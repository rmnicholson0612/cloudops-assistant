import json
import logging
import re
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import auth_required
except ImportError:

    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
try:
    bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
except Exception as e:
    logger.warning(f"Bedrock client initialization failed: {e}")
    bedrock = None

dynamodb = boto3.resource("dynamodb")
plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")


def lambda_handler(event, context):
    """AI Terraform Explainer - Analyze and explain terraform plans"""
    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if method == "POST" and "/ai/explain" in path:
            return explain_terraform_plan(event)
        elif method == "GET" and "/ai/explanations" in path:
            return get_plan_explanations(event)
        else:
            return error_response("Invalid endpoint", 404)

    except Exception as e:
        logger.error(f"AI explainer error: {str(e)}")
        return error_response("Internal server error")


def explain_terraform_plan(event):
    """Generate AI explanation for a terraform plan"""
    try:
        body = json.loads(event.get("body", "{}"))
        user_id = event["user_info"]["user_id"]

        plan_id = body.get("plan_id")
        if not plan_id:
            return error_response("plan_id is required")

        # Sanitize plan_id to prevent injection
        sanitized_plan_id = str(plan_id).strip()[:100]

        # Validate plan_id format (alphanumeric, hyphens, underscores only)
        if not re.match(r"^[a-zA-Z0-9._-]+$", sanitized_plan_id):
            return error_response("Invalid plan_id format")

        # Get terraform plan from DynamoDB
        response = plans_table.get_item(Key={"plan_id": sanitized_plan_id})
        if "Item" not in response:
            return error_response("Plan not found", 404)

        plan_item = response["Item"]

        # Verify user owns this plan
        if plan_item.get("user_id") != user_id:
            return error_response("Access denied", 403)

        plan_content = plan_item.get("plan_content", "")
        if not plan_content:
            return error_response("No plan content to analyze")

        # Generate AI explanation
        explanation = generate_ai_explanation(plan_content)

        # Store explanation back to DynamoDB
        plans_table.update_item(
            Key={"plan_id": sanitized_plan_id},
            UpdateExpression="SET ai_explanation = :explanation, ai_analyzed_at = :timestamp",
            ExpressionAttributeValues={
                ":explanation": explanation,
                ":timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return success_response(
            {
                "plan_id": sanitized_plan_id,
                "explanation": explanation,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Error explaining plan: {str(e)}")
        return error_response("Failed to explain terraform plan")


def get_plan_explanations(event):
    """Get AI explanations for user's plans"""
    try:
        user_id = event["user_info"]["user_id"]

        # Validate and sanitize user_id
        if not user_id or not isinstance(user_id, str):
            return error_response("Invalid user ID")

        sanitized_user_id = str(user_id).strip()[:100]
        if not re.match(r"^[a-zA-Z0-9._@-]+$", sanitized_user_id):
            return error_response("Invalid user ID format")

        # Get plans with AI explanations using GSI if available, otherwise scan
        try:
            # Try to use GSI for better performance
            response = plans_table.query(
                IndexName="user_id-timestamp-index",
                KeyConditionExpression="user_id = :user_id",
                FilterExpression="attribute_exists(ai_explanation)",
                ExpressionAttributeValues={":user_id": sanitized_user_id},
                Limit=50,
                ScanIndexForward=False,  # Most recent first
            )
        except Exception:
            # Fallback to scan if GSI doesn't exist
            response = plans_table.scan(
                FilterExpression="user_id = :user_id AND attribute_exists(ai_explanation)",
                ExpressionAttributeValues={":user_id": sanitized_user_id},
                Limit=50,
            )

        explanations = []
        for item in response.get("Items", []):
            explanations.append(
                {
                    "plan_id": item["plan_id"],
                    "repo_name": item.get("repo_name", ""),
                    "timestamp": item.get("timestamp", ""),
                    "ai_explanation": item.get("ai_explanation", {}),
                    "ai_analyzed_at": item.get("ai_analyzed_at", ""),
                }
            )

        # Sort by most recent
        explanations.sort(key=lambda x: x.get("ai_analyzed_at", ""), reverse=True)

        return success_response(
            {"explanations": explanations, "total": len(explanations)}
        )

    except Exception as e:
        logger.error(f"Error getting explanations: {str(e)}")
        return error_response("Failed to get explanations")


def generate_ai_explanation(plan_content):
    """Use AWS Bedrock to generate terraform plan explanation"""
    try:
        if not bedrock:
            raise Exception("Bedrock client not available")

        prompt = f"""Analyze this Terraform plan and provide a clear explanation:

{plan_content[:4000]}

Provide:
1. Summary of changes
2. Risk level (LOW/MEDIUM/HIGH)
3. Impact assessment
4. Recommendations

Format as JSON with keys: summary, risk_level, impact, recommendations (array)"""

        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0",
            body=json.dumps(
                {
                    "messages": [{"role": "user", "content": [{"text": prompt}]}],
                    "inferenceConfig": {"maxTokens": 1000, "temperature": 0.3},
                }
            ),
        )

        result = json.loads(response["body"].read().decode("utf-8"))
        ai_text = result["output"]["message"]["content"][0]["text"]

        try:
            return json.loads(ai_text)
        except Exception:
            return {
                "summary": ai_text,
                "risk_level": "MEDIUM",
                "impact": "Review required",
                "recommendations": ["Review plan manually"],
            }

    except Exception as e:
        logger.error(f"AI explanation error: {str(e)}")
        raise


def analyze_plan_fallback(plan_content, error_msg):
    """Detailed fallback analysis when Bedrock is unavailable"""
    try:
        logger.info(f"Fallback analysis starting, plan length: {len(plan_content)}")

        # Clean content for better parsing - more comprehensive ANSI removal
        clean_content = re.sub(r"\x1b\[[0-9;]*[mK]", "", plan_content)
        clean_content = re.sub(r"\[\d+m", "", clean_content)  # Additional cleanup
        lines = clean_content.split("\n")

        logger.info(f"Cleaned content length: {len(clean_content)}")

        # Parse detailed resource changes
        resource_changes = []
        current_resource = None
        in_resource_block = False

        for i, line in enumerate(lines):
            # Detect resource headers
            if "will be created" in line:
                match = re.search(r"#\s+([^\s]+)\s+will be created", line)
                if match:
                    current_resource = {
                        "name": match.group(1),
                        "action": "CREATE",
                        "details": [],
                    }
                    in_resource_block = True
            elif "will be updated in-place" in line:
                match = re.search(
                    r"#\s+([^\s\[]+)", line
                )  # Stop at [ to avoid ANSI codes
                if match:
                    resource_name = re.sub(
                        r"\[\d+m", "", match.group(1)
                    )  # Clean any remaining codes
                    current_resource = {
                        "name": resource_name,
                        "action": "UPDATE",
                        "details": [],
                    }
                    in_resource_block = True
            elif "will be destroyed" in line:
                match = re.search(r"#\s+([^\s]+)\s+will be destroyed", line)
                if match:
                    current_resource = {
                        "name": match.group(1),
                        "action": "DESTROY",
                        "details": [],
                    }
                    in_resource_block = True
            elif "must be replaced" in line:
                match = re.search(r"#\s+([^\s]+)\s+must be replaced", line)
                if match:
                    current_resource = {
                        "name": match.group(1),
                        "action": "REPLACE",
                        "details": [],
                    }
                    in_resource_block = True

            # Parse resource details
            if in_resource_block and current_resource:
                # Look for attribute changes
                if "~" in line and "=" in line and "->" in line:
                    # Extract attribute changes like: ~ tags = { "Environment" = "Dev"
                    # -> "winterfell" }
                    attr_match = re.search(
                        r'~\s*([^=]+)\s*=.*?"([^"]+)"\s*->\s*"([^"]+)"', line
                    )
                    if attr_match:
                        attr_name = attr_match.group(1).strip()
                        old_val = attr_match.group(2)
                        new_val = attr_match.group(3)
                        current_resource["details"].append(
                            f"{attr_name}: '{old_val}' → '{new_val}'"
                        )
                elif "+" in line and "=" in line:
                    # New attributes
                    attr_match = re.search(r'\+\s*([^=]+)\s*=\s*"?([^"\n]+)"?', line)
                    if attr_match:
                        attr_name = attr_match.group(1).strip()
                        value = attr_match.group(2).strip()
                        current_resource["details"].append(
                            f"Adding {attr_name}: {value}"
                        )
                elif "-" in line and "=" in line:
                    # Removed attributes
                    attr_match = re.search(r'-\s*([^=]+)\s*=\s*"?([^"\n]+)"?', line)
                    if attr_match:
                        attr_name = attr_match.group(1).strip()
                        value = attr_match.group(2).strip()
                        current_resource["details"].append(
                            f"Removing {attr_name}: {value}"
                        )

                # End of resource block
                if line.strip() == "}" or (
                    line.strip() == ""
                    and i < len(lines) - 1
                    and lines[i + 1].strip().startswith("#")
                ):
                    if current_resource:
                        resource_changes.append(current_resource)
                        current_resource = None
                        in_resource_block = False

        # Add any remaining resource
        if current_resource:
            resource_changes.append(current_resource)

        # Count changes
        resources_created = len(
            [r for r in resource_changes if r["action"] == "CREATE"]
        )
        resources_modified = len(
            [r for r in resource_changes if r["action"] == "UPDATE"]
        )
        resources_destroyed = len(
            [r for r in resource_changes if r["action"] in ["DESTROY", "REPLACE"]]
        )
        total_changes = len(resource_changes)

        logger.info(
            f"Resource changes found: {total_changes} total, "
            f"{resources_created} created, {resources_modified} modified, "
            f"{resources_destroyed} destroyed"
        )
        logger.info(f"Resource changes details: {resource_changes}")

        # Check for "No changes" message
        has_no_changes = (
            "No changes" in plan_content and "infrastructure matches" in plan_content
        )
        logger.info(
            f"No changes check: 'No changes' in content: "
            f"{'No changes' in plan_content}, 'infrastructure matches' "
            f"in content: {'infrastructure matches' in plan_content}, "
            f"combined: {has_no_changes}"
        )

        if has_no_changes:
            logger.info("Returning no changes result")
            return {
                "summary": "No infrastructure changes detected. Your current infrastructure matches the Terraform configuration.",
                "resources": [],
                "risk_level": "LOW",
                "impact": "No impact - no changes will be made",
                "recommendations": ["✅ Infrastructure is up to date"],
                "fallback_analysis": True,
            }

        # Generate detailed resource descriptions
        resource_descriptions = []
        for change in resource_changes[:5]:  # Limit to 5 for readability
            if change["action"] == "UPDATE" and change["details"]:
                details_str = ", ".join(change["details"][:3])  # Limit details
                resource_descriptions.append(f"🔄 {change['name']}: {details_str}")
            elif change["action"] == "CREATE":
                resource_descriptions.append(
                    f"➕ {change['name']}: New resource will be created"
                )
            elif change["action"] == "DESTROY":
                resource_descriptions.append(
                    f"❌ {change['name']}: Resource will be destroyed"
                )
            elif change["action"] == "REPLACE":
                resource_descriptions.append(
                    f"🔄 {change['name']}: Resource will be replaced (destroy + create)"
                )

        # Determine risk level
        if resources_destroyed > 0:
            risk_level = "HIGH"
        elif any(
            "security" in str(change).lower() or "policy" in str(change).lower()
            for change in resource_changes
        ):
            risk_level = "MEDIUM"
        elif total_changes > 0:
            risk_level = "LOW"
        else:
            risk_level = "LOW"

        # Generate summary
        if total_changes == 0:
            summary = "No infrastructure changes detected in this terraform plan."
        elif total_changes == 1 and resources_modified == 1:
            # Special case for single updates
            change = resource_changes[0]
            if change["details"]:
                summary = (
                    f"Single update to {change['name']}: "
                    f"{', '.join(change['details'][:2])}"
                )
            else:
                summary = f"Single update to {change['name']}"
        else:
            summary = (
                f"Plan will modify {total_changes} resources: "
                f"{resources_created} new, {resources_modified} updated, "
                f"{resources_destroyed} destroyed."
            )

        # Generate impact analysis
        if resources_destroyed > 0:
            impact = "⚠️ DESTRUCTIVE: Some resources will be deleted - this may cause downtime"
        elif resources_modified > 0:
            impact = "Configuration changes will be applied - minimal impact expected"
        elif resources_created > 0:
            impact = (
                "New resources will be added - no impact to existing infrastructure"
            )
        else:
            impact = "No impact - no changes will be made"

        # Generate recommendations
        recommendations = []
        if resources_destroyed > 0:
            recommendations.append(
                "🚨 CRITICAL: Backup data before applying - resources will be destroyed"
            )
        if any("tag" in str(change).lower() for change in resource_changes):
            recommendations.append(
                "📋 Tag changes detected - verify billing and organization impact"
            )
        if resources_modified > 0:
            recommendations.append(
                "🔍 Review changes carefully and test in non-production first"
            )
        if total_changes > 0:
            recommendations.append(
                "✅ Run 'terraform plan' again before apply to confirm changes"
            )
        else:
            recommendations.append("✅ No action needed - infrastructure is up to date")

        result = {
            "summary": summary,
            "resources": resource_descriptions,
            "risk_level": risk_level,
            "impact": impact,
            "recommendations": recommendations,
            "fallback_analysis": True,
        }

        logger.info(f"Fallback analysis result: {result}")
        return result

    except Exception as fallback_error:
        logger.error(f"Fallback analysis failed: {str(fallback_error)}")
        return {
            "summary": "Basic analysis completed - review plan manually for details",
            "resources": ["Unable to parse specific resource changes"],
            "risk_level": "MEDIUM",
            "impact": "Unknown impact - manual review required",
            "recommendations": [
                "📖 Review the terraform plan output manually before applying"
            ],
            "fallback_analysis": True,
        }


def success_response(data):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(data, default=str),
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps({"error": message}),
    }


def cors_response():
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": "",
    }
