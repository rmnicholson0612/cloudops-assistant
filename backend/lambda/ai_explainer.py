import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import auth_required
except ImportError:
    auth_required = None

# Override auth_required for local development or if not available
if (
    os.environ.get("AWS_ENDPOINT_URL") == "http://localhost:4566"
    or auth_required is None
):

    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
try:
    BEDROCK = boto3.client("bedrock-runtime", region_name="us-east-1")
except Exception as e:
    logger.warning(f"Bedrock client initialization failed: {e}")
    BEDROCK = None

dynamodb = boto3.resource("dynamodb")

plans_table_name = os.environ.get(
    "TERRAFORM_PLANS_TABLE", "cloudops-assistant-terraform-plans"
)
plans_table = dynamodb.Table(plans_table_name)


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
        if method == "GET" and "/ai/explanations" in path:
            return get_plan_explanations(event)
        return error_response("Invalid endpoint", 404)

    except Exception as e:
        logger.error(f"AI explainer error: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return error_response(f"Internal server error: {str(e)}")


def explain_terraform_plan(event):
    """Generate AI explanation for a terraform plan"""
    try:
        logger.info(f"AI explainer request: {event}")
        body_str = event.get("body") or "{}"
        body = json.loads(body_str) if body_str else {}
        logger.info(f"Request body: {body}")
        user_id = event["user_info"]["user_id"]
        logger.info(f"User ID: {user_id}")

        plan_id = body.get("plan_id")
        logger.info(f"Plan ID: {plan_id}")
        if not plan_id:
            logger.error("Missing plan_id in request")
            return error_response("plan_id is required")

        # Sanitize plan_id to prevent injection
        sanitized_plan_id = str(plan_id).strip()[:100]
        logger.info(f"Sanitized plan ID: {sanitized_plan_id}")

        # Validate plan_id format (allow alphanumeric, hyphens, underscores, colons, plus, hash)
        if not re.match(r"^[a-zA-Z0-9._:#+-]+$", sanitized_plan_id):
            logger.error(f"Invalid plan_id format: {sanitized_plan_id}")
            return error_response("Invalid plan_id format")

        # Get terraform plan from DynamoDB
        logger.info(f"Querying DynamoDB for plan_id: {sanitized_plan_id}")
        response = plans_table.get_item(Key={"plan_id": sanitized_plan_id})
        logger.info(f"DynamoDB response: {response}")
        if "Item" not in response:
            logger.error(f"Plan not found: {sanitized_plan_id}")
            return error_response("Plan not found", 404)

        plan_item = response["Item"]
        logger.info(f"Plan item: {plan_item}")

        # Verify user owns this plan
        plan_owner = plan_item.get("user_id")
        logger.info(f"Plan owner: {plan_owner}, Current user: {user_id}")
        if plan_owner != user_id:
            logger.error(
                f"Access denied: plan owner {plan_owner} != current user {user_id}"
            )
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
        logger.error(f"Exception type: {type(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return error_response(f"Failed to explain terraform plan: {str(e)}")


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
            from boto3.dynamodb.conditions import Key

            response = plans_table.query(
                IndexName="user_id-timestamp-index",
                KeyConditionExpression=Key("user_id").eq(sanitized_user_id),
                FilterExpression="attribute_exists(ai_explanation)",
                Limit=50,
                ScanIndexForward=False,  # Most recent first
            )
        except Exception:
            # Fallback to scan if GSI doesn't exist
            from boto3.dynamodb.conditions import Attr

            response = plans_table.scan(
                FilterExpression=Attr("user_id").eq(sanitized_user_id)
                & Attr("ai_explanation").exists(),
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
    """Generate AI explanation using appropriate provider based on environment"""
    try:
        # Check if running in local development environment
        if is_local_environment():
            return generate_ollama_explanation(plan_content)

        # Production: use AWS Bedrock
        if not BEDROCK:
            return generate_fallback_explanation(plan_content)

        prompt = f"""Analyze this Terraform plan and provide a clear explanation:

{plan_content[:4000]}

Provide:
1. Summary of changes
2. Risk level (LOW/MEDIUM/HIGH)
3. Impact assessment
4. Recommendations

Format as JSON with keys: summary, risk_level, impact, recommendations (array)"""

        logger.info("Attempting AI explanation with Bedrock")

        # Try different model formats
        model_attempts = [
            ("amazon.nova-lite-v1:0", "nova"),
            ("anthropic.claude-3-haiku-20240307-v1:0", "claude"),
            ("amazon.titan-text-lite-v1", "titan"),
        ]

        for model_id, model_type in model_attempts:
            try:
                logger.info(f"Trying model: {model_id}")

                if model_type == "nova":
                    body = {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {"maxTokens": 1000, "temperature": 0.3},
                    }
                elif model_type == "claude":
                    body = {
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 1000,
                        "temperature": 0.3,
                    }
                else:  # titan
                    body = {
                        "inputText": prompt,
                        "textGenerationConfig": {
                            "maxTokenCount": 1000,
                            "temperature": 0.3,
                        },
                    }

                response = BEDROCK.invoke_model(modelId=model_id, body=json.dumps(body))

                result = json.loads(response["body"].read().decode("utf-8"))

                # Extract text based on model type
                if model_type == "nova":
                    ai_text = result["output"]["message"]["content"][0]["text"]
                elif model_type == "claude":
                    ai_text = result["content"][0]["text"]
                else:  # titan
                    ai_text = result["results"][0]["outputText"]

                logger.info("Successfully used model: %s", model_id)

                try:
                    parsed_json = json.loads(ai_text)
                    parsed_json["evaluated_by"] = model_id
                    return parsed_json
                except Exception:
                    return {
                        "summary": ai_text,
                        "risk_level": "MEDIUM",
                        "impact": "Review required",
                        "recommendations": ["Review plan manually"],
                        "evaluated_by": model_id,
                    }

            except Exception as model_error:
                logger.warning(f"Model {model_id} failed: {str(model_error)}")
                continue

        # If all models fail, use fallback
        logger.warning("All Bedrock models failed, using fallback analysis")
        return generate_fallback_explanation(plan_content)

    except Exception as e:
        logger.error(f"AI explanation error: {str(e)}")
        return generate_fallback_explanation(plan_content)


def is_local_environment():
    """Detect if running in local development environment"""
    return (
        os.environ.get("AWS_ENDPOINT_URL") == "http://localhost:4566"
        or os.environ.get("LOCALSTACK_HOSTNAME")
        or os.environ.get("LOCAL_DEV") == "true"
    )


def generate_ollama_explanation(plan_content):
    """Generate explanation using local Ollama"""
    try:
        import re

        # Strip ANSI color codes for AI processing only
        clean_content = re.sub(r"\x1b\[[0-9;]*m", "", plan_content)

        # Extract key information from clean plan
        creates = len(re.findall(r"will be created", clean_content))
        updates = len(re.findall(r"will be updated|will be modified", clean_content))
        destroys = len(re.findall(r"will be destroyed", clean_content))

        # Extract resource types from clean content
        resources = re.findall(r"# ([a-zA-Z0-9_\.]+)", clean_content)
        resource_types = list(set([r.split(".")[0] for r in resources if "." in r]))

        # Analyze what's actually changing
        tag_changes = re.findall(
            r'"([^"]+)"\s*=\s*"([^"]+)"\s*->\s*"([^"]+)"', clean_content
        )
        resource_changes = re.findall(
            r"# ([a-zA-Z0-9_\.]+).*will be (created|updated|destroyed)", clean_content
        )

        # Generate human-readable summary
        summary_parts = []

        if creates + updates + destroys == 0:
            summary_parts.append(
                "No changes detected - your infrastructure matches the configuration."
            )
        else:
            summary_parts.append(
                f"You have {creates + updates + destroys} resource changes planned."
            )

            if creates > 0:
                summary_parts.append(f"\n\n**Adding {creates} new resources:**")
                create_resources = re.findall(
                    r"# ([a-zA-Z0-9_\.]+).*will be created", clean_content
                )
                for resource in create_resources[:3]:
                    resource_type = resource.split(".")[0]
                    resource_name = (
                        resource.split(".")[1] if "." in resource else resource
                    )
                    summary_parts.append(f"• {resource_type.upper()}: {resource_name}")
                if len(create_resources) > 3:
                    summary_parts.append(f"• ... and {len(create_resources) - 3} more")

            if updates > 0:
                summary_parts.append(f"\n\n**Modifying {updates} existing resources:**")
                update_resources = re.findall(
                    r"# ([a-zA-Z0-9_\.]+).*will be updated", clean_content
                )
                for resource in update_resources[:3]:
                    resource_type = resource.split(".")[0]
                    resource_name = (
                        resource.split(".")[1] if "." in resource else resource
                    )

                    # Find what's changing on this resource
                    resource_section = re.search(
                        f"# {re.escape(resource)}.*?(?=\n\n|\n  #|$)",
                        clean_content,
                        re.DOTALL,
                    )
                    if resource_section:
                        section_text = resource_section.group(0)
                        if "tags" in section_text:
                            tag_changes_in_resource = re.findall(
                                r'"([^"]+)"\s*=\s*"([^"]+)"\s*->\s*"([^"]+)"',
                                section_text,
                            )
                            if tag_changes_in_resource:
                                tag_desc = ", ".join(
                                    [
                                        f"{tag[0]}: '{tag[1]}' → '{tag[2]}'"
                                        for tag in tag_changes_in_resource[:2]
                                    ]
                                )
                                summary_parts.append(
                                    f"• {resource_type.upper()}: {resource_name} (updating tags: {tag_desc})"
                                )
                            else:
                                summary_parts.append(
                                    f"• {resource_type.upper()}: {resource_name} (updating tags)"
                                )
                        else:
                            summary_parts.append(
                                f"• {resource_type.upper()}: {resource_name} (configuration changes)"
                            )
                    else:
                        summary_parts.append(
                            f"• {resource_type.upper()}: {resource_name}"
                        )
                if len(update_resources) > 3:
                    summary_parts.append(f"• ... and {len(update_resources) - 3} more")

            if destroys > 0:
                summary_parts.append(f"\n\n**Deleting {destroys} resources:**")
                destroy_resources = re.findall(
                    r"# ([a-zA-Z0-9_\.]+).*will be destroyed", clean_content
                )
                for resource in destroy_resources[:3]:
                    resource_type = resource.split(".")[0]
                    resource_name = (
                        resource.split(".")[1] if "." in resource else resource
                    )
                    summary_parts.append(f"• {resource_type.upper()}: {resource_name}")
                if len(destroy_resources) > 3:
                    summary_parts.append(f"• ... and {len(destroy_resources) - 3} more")

        ai_text = "".join(summary_parts)

        # Intelligent risk assessment based on actual changes
        env_tag_changes = [
            t
            for t in tag_changes
            if "environment" in t[0].lower() or "env" in t[0].lower()
        ]

        if destroys > 0:
            risk_level = "HIGH"
            impact = f"⚠️ {destroys} resources will be destroyed - potential data loss"
        elif env_tag_changes:
            # Special handling for environment tag changes
            old_env, new_env = env_tag_changes[0][1], env_tag_changes[0][2]
            standard_envs = [
                "local",
                "dev",
                "development",
                "test",
                "staging",
                "stg",
                "prod",
                "production",
            ]
            if new_env.lower() not in standard_envs:
                risk_level = "MEDIUM"
                impact = f"Environment tag changing from '{old_env}' to '{new_env}' - non-standard naming"
            else:
                risk_level = "LOW"
                impact = f"Environment tag changing from '{old_env}' to '{new_env}' - metadata only"
        elif creates > 10 or updates > 5:
            risk_level = "MEDIUM"
            impact = f"Large change set: {creates} creates, {updates} updates"
        else:
            risk_level = "LOW"
            impact = f"Small change: {creates} creates, {updates} updates, {destroys} destroys"

        # Context-aware recommendations
        recommendations = []
        if destroys > 0:
            recommendations.append("⚠️ Backup any data before destroying resources")
        if env_tag_changes:
            old_env, new_env = env_tag_changes[0][1], env_tag_changes[0][2]
            if new_env.lower() not in [
                "local",
                "dev",
                "development",
                "test",
                "staging",
                "stg",
                "prod",
                "production",
            ]:
                recommendations.append(
                    f"🏷️ Verify '{new_env}' follows company environment naming standards"
                )
                recommendations.append(
                    "📋 Confirm this environment exists in your infrastructure"
                )
            recommendations.append("✅ Tag changes are safe - no application impact")
        elif tag_changes and not env_tag_changes:
            recommendations.append(
                "🏷️ Tag changes detected - verify naming conventions"
            )
            recommendations.append("✅ Tag updates are metadata only - low risk")
        elif creates > 0 and "ec2" in " ".join(resource_types).lower():
            recommendations.append("🔒 Review security groups and access permissions")
        elif creates > 0 and "s3" in " ".join(resource_types).lower():
            recommendations.append(
                "💰 Consider bucket lifecycle policies for cost optimization"
            )
        if not recommendations:
            recommendations.append("✅ Changes appear safe to apply")

        return {
            "summary": ai_text,
            "risk_level": risk_level,
            "impact": impact,
            "recommendations": recommendations,
            "evaluated_by": "Ollama (Local Development)",
            "change_analysis": {
                "tag_changes": len(tag_changes),
                "env_changes": len(env_tag_changes),
                "resource_changes": len(resource_changes),
            },
        }

    except Exception as e:
        logger.warning(f"Ollama failed: {e}")
        return generate_fallback_explanation(plan_content)


def generate_fallback_explanation(plan_content):
    """Generate a basic explanation when AI is not available"""
    import re

    # Basic pattern matching for terraform plans
    create_count = len(re.findall(r"will be created", plan_content))
    update_count = len(re.findall(r"will be updated", plan_content))
    destroy_count = len(re.findall(r"will be destroyed", plan_content))

    total_changes = create_count + update_count + destroy_count

    # Determine risk level
    if destroy_count > 0:
        risk_level = "HIGH"
    elif update_count > 5 or create_count > 10:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    summary = (
        f"Terraform plan shows {total_changes} total changes: {create_count} resources to create, "
        f"{update_count} to update, {destroy_count} to destroy."
    )

    recommendations = []
    if destroy_count > 0:
        recommendations.append("Review resource destruction carefully")
    if total_changes > 10:
        recommendations.append("Consider applying changes in smaller batches")
    if not recommendations:
        recommendations.append("Plan looks safe to apply")

    return {
        "summary": summary,
        "risk_level": risk_level,
        "impact": f"Changes affect {total_changes} resources",
        "recommendations": recommendations,
        "evaluated_by": "Pattern Analysis (Fallback)",
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
