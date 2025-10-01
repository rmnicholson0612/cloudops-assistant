import json
import logging
import os
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key as DynamoKey

# Force rebuild - fixing import issue

try:
    from auth_utils import auth_required
except ImportError:

    def auth_required(func):
        return func


# Set up logging to see what's happening
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)

# Module-level DynamoDB resource for connection reuse
dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    """Manage drift monitoring configuration"""
    # Sanitize log inputs to prevent log injection (CWE-117)
    import re

    safe_method = re.sub(r"[\r\n\t]", "", str(event.get("httpMethod", "UNKNOWN"))[:20])
    safe_path = re.sub(r"[\r\n\t]", "", str(event.get("path", "UNKNOWN"))[:100])
    logger.info(f"Lambda handler called with method: {safe_method}, path: {safe_path}")

    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    # Check if user_info is already in event (for local development)
    if "user_info" not in event:
        # Apply auth_required decorator logic manually for non-OPTIONS requests
        try:
            from auth_utils import verify_jwt_token

            user_info, error = verify_jwt_token(event)
            if error:
                logger.error(f"JWT verification failed: {error}")
                return {
                    "statusCode": 401,
                    "headers": get_cors_headers(),
                    "body": json.dumps({"error": error}),
                }

            event["user_info"] = user_info
            logger.info(f"JWT verification successful, user_info: {user_info}")
        except Exception as e:
            logger.error(f"Auth error: {str(e)}")
            return {
                "statusCode": 401,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Authentication failed"}),
            }
    else:
        logger.info(f"Using existing user_info from event: {event['user_info']}")

    try:
        method = event.get("httpMethod")
        path = event.get("path", "")
        logger.info(f"Processing {method} request to {path}")

        if method == "POST" and "/drift/configure" in path:
            return configure_drift_monitoring(event)
        elif method == "GET" and "/drift/status" in path:
            return get_drift_status(event)
        elif method == "POST" and "/drift/scan" in path:
            return run_manual_scan(event)
        elif method == "PUT" and "/drift/update" in path:
            return update_drift_config(event)
        elif method == "DELETE" and "/drift/delete" in path:
            return delete_drift_config(event)
        else:
            logger.error(f"Invalid endpoint: {method} {path}")
            return error_response("Invalid endpoint")

    except Exception as e:
        logger.error(f"Error in drift config handler: {str(e)}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return error_response(f"Internal server error: {str(e)}")


def configure_drift_monitoring(event):
    """Configure a repository for drift monitoring"""
    try:
        body_str = event.get("body") or "{}"
        body = json.loads(body_str) if body_str else {}

        # Secure user ID extraction and sanitization
        user_id = str(event["user_info"]["user_id"]).strip()
        import re

        user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:50]
        if not user_id:
            return error_response("Invalid user ID", 401)

        # Secure input sanitization and validation
        # Sanitize repo_name - only allow alphanumeric, hyphens, underscores
        repo_name = (
            str(body.get("repo_name", "")).strip() if body.get("repo_name") else None
        )
        if repo_name:
            repo_name = re.sub(r"[^a-zA-Z0-9_-]", "", repo_name)[:100]
            if not repo_name:
                return error_response("Invalid repository name format")

        # Validate GitHub URL more strictly
        github_url = (
            str(body.get("github_url", "")).strip() if body.get("github_url") else None
        )
        if github_url:
            # Only allow HTTPS GitHub URLs with proper format
            github_pattern = (
                r"^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:\.git)?/?$"
            )
            if not re.match(github_pattern, github_url) or len(github_url) > 500:
                return error_response("Invalid GitHub URL format")

        # Sanitize terraform directory path
        terraform_dir = str(body.get("terraform_dir", ".")).strip()[:100]
        # Prevent path traversal attacks
        if (
            os.path.isabs(terraform_dir)
            or ".." in terraform_dir
            or terraform_dir.startswith("/")
            or not re.match(r"^[a-zA-Z0-9._/-]+$", terraform_dir)
        ):
            return error_response("Invalid terraform directory path")

        # Validate schedule with whitelist
        schedule = str(body.get("schedule", "daily")).strip().lower()
        if schedule not in ["daily", "hourly"]:
            return error_response("Invalid schedule. Must be 'daily' or 'hourly'")

        # Sanitize and validate email
        alert_email = (
            str(body.get("alert_email", "")).strip()
            if body.get("alert_email")
            else None
        )
        if alert_email:
            # Strict email validation
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, alert_email) or len(alert_email) > 100:
                return error_response("Invalid email format")

        # Additional validation already handled above

        if not repo_name or not github_url:
            return error_response("repo_name and github_url are required")

        # Create SNS topic for alerts if email provided
        alert_topic_arn = None
        if alert_email:
            alert_topic_arn = create_alert_topic(user_id, repo_name, alert_email)
            if not alert_topic_arn:
                logger.warning(
                    f"Failed to create SNS topic for {alert_email}, "
                    "continuing without alerts"
                )

        # Store configuration
        drift_table_name = os.environ.get(
            "DRIFT_CONFIG_TABLE", "cloudops-assistant-drift-config"
        )
        table = dynamodb.Table(drift_table_name)

        config_id = f"{user_id}#{repo_name}"

        table.put_item(
            Item={
                "config_id": config_id,
                "user_id": user_id,
                "repo_name": repo_name,
                "github_url": github_url,
                "terraform_dir": terraform_dir,
                "schedule": schedule,
                "alert_topic_arn": alert_topic_arn,
                "alert_email": alert_email,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
            }
        )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {
                    "message": "Drift monitoring configured successfully",
                    "config_id": config_id,
                    "schedule": schedule,
                },
                default=decimal_default,
            ),
        }

    except Exception as e:
        logger.error(f"Error configuring drift monitoring: {str(e)}")
        return error_response("Failed to configure drift monitoring")


def get_drift_status(event):
    """Get drift monitoring status for user's repositories"""
    try:
        logger.info(f"Event received: {json.dumps(event, default=str)[:500]}...")
        logger.info(f"Event user_info: {event.get('user_info', 'NOT_FOUND')}")

        user_id = str(event["user_info"]["user_id"]).strip()
        logger.info(f"Getting drift status for user_id: '{user_id}'")

        drift_table_name = os.environ.get(
            "DRIFT_CONFIG_TABLE", "cloudops-assistant-drift-config"
        )
        plans_table_name = os.environ.get(
            "TERRAFORM_PLANS_TABLE", "cloudops-assistant-terraform-plans"
        )
        config_table = dynamodb.Table(drift_table_name)

        # Query configurations using GSI
        try:
            logger.info(
                f"Querying GSI with user_id: '{user_id}' (type: {type(user_id)})"
            )
            response = config_table.query(
                IndexName="user-id-index",
                KeyConditionExpression=DynamoKey("user_id").eq(user_id),
                Limit=50,
            )
            configs = response.get("Items", [])
            logger.info(
                f"GSI query successful, found {len(configs)} configs for user_id: {user_id}"
            )
            logger.info(f"Query response: {json.dumps(response, default=str)[:200]}...")
        except Exception as gsi_error:
            logger.error(f"GSI query failed for user_id '{user_id}': {gsi_error}")
            logger.error(f"Exception type: {type(gsi_error)}")
            logger.error(
                f"Exception args: {gsi_error.args if hasattr(gsi_error, 'args') else 'No args'}"
            )
            return error_response(f"Database query failed: {str(gsi_error)}")

        # Get recent drift results
        plans_table = dynamodb.Table(plans_table_name)

        for config in configs:
            # Get latest scan result with parameterized query
            # Sanitize repo_name from database record
            repo_name = str(config.get("repo_name", "")).strip()
            if repo_name:
                try:
                    plan_response = plans_table.query(
                        IndexName="repo-timestamp-index",
                        KeyConditionExpression=DynamoKey("repo_name").eq(repo_name),
                        ScanIndexForward=False,
                        Limit=1,
                    )
                    latest_scan = plan_response.get("Items", [])
                    if latest_scan:
                        config["last_scan"] = latest_scan[0]
                    else:
                        config["last_scan"] = None
                except Exception as plan_error:
                    logger.error(
                        f"Failed to get latest scan for {repo_name}: {plan_error}"
                    )
                    # Don't fail the whole request, just log the error
                    config["last_scan"] = None
            else:
                config["last_scan"] = None

        # Convert all Decimal objects to float before JSON serialization
        def convert_decimals(obj):
            if isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: convert_decimals(value) for key, value in obj.items()}
            elif isinstance(obj, Decimal):
                return float(obj)
            else:
                return obj

        converted_configs = convert_decimals(configs)

        logger.info(
            f"Final result: Found {len(configs)} drift configurations for user {user_id}"
        )
        for config in configs:
            logger.info(
                f"Config: {config.get('config_id')} - {config.get('repo_name')}"
            )

        if len(configs) == 0:
            logger.warning(
                f"No configurations found for user_id '{user_id}' - this might indicate an authentication or query issue"
            )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {"configurations": converted_configs, "total_repos": len(configs)}
            ),
        }

    except Exception as e:
        logger.error(f"Error getting drift status: {str(e)}")
        logger.error(f"Exception type: {type(e)}")
        logger.error(f"Exception args: {e.args if hasattr(e, 'args') else 'No args'}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        return error_response(f"Failed to get drift status: {str(e)}")


def run_manual_scan(event):
    """Trigger manual drift scan for a repository"""
    try:
        # Secure user ID and config ID handling
        user_id = str(event["user_info"]["user_id"]).strip()
        import re

        user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:50]
        if not user_id:
            return error_response("Invalid user ID", 401)

        config_id = event.get("pathParameters", {}).get("config_id")
        if config_id:
            # Sanitize config_id to prevent injection
            config_id = str(config_id).strip()[:200]
            # Allow URL-encoded characters (% followed by hex digits) in addition to safe characters
            if not re.match(r"^[a-zA-Z0-9_#%-]+$", config_id):
                return error_response("Invalid config ID format", 400)

        if not config_id:
            logger.error("No config_id in path parameters")
            return error_response("Missing config_id parameter", 400)

        # URL decode the config_id in case it's double-encoded
        import urllib.parse

        config_id = urllib.parse.unquote(config_id)

        logger.info(f"Manual scan - user_id: {user_id}, config_id: {config_id}")
        logger.info(f"Event path: {event.get('path', 'No path')}")
        logger.info(
            f"Event pathParameters: "
            f"{event.get('pathParameters', 'No pathParameters')}"
        )

        # Get configuration
        drift_table_name = os.environ.get(
            "DRIFT_CONFIG_TABLE", "cloudops-assistant-drift-config"
        )
        config_table = dynamodb.Table(drift_table_name)
        response = config_table.get_item(Key={"config_id": config_id})

        if "Item" not in response:
            logger.error(f"Configuration not found: {config_id}")
            # Try to find by user_id if direct lookup fails
            user_configs = config_table.query(
                IndexName="user-id-index",
                KeyConditionExpression=DynamoKey("user_id").eq(user_id),
            )
            logger.info(
                f"Found {len(user_configs.get('Items', []))} configs for user {user_id}"
            )
            for cfg in user_configs.get("Items", []):
                logger.info(f"Available config_id: {cfg.get('config_id')}")
            return error_response("Configuration not found", 404)

        config = response["Item"]

        # Verify ownership
        if config.get("user_id") != user_id:
            logger.error(
                f"Unauthorized access - config user_id: {config.get('user_id')}, "
                f"request user_id: {user_id}"
            )
            return error_response("Unauthorized", 403)

        # Run real terraform scan
        drift_result = execute_terraform_scan(
            config["github_url"], config["terraform_dir"]
        )

        # Store scan result
        plans_table_name = os.environ.get(
            "TERRAFORM_PLANS_TABLE", "cloudops-assistant-terraform-plans"
        )
        plans_table = dynamodb.Table(plans_table_name)
        plan_id = (
            f"{config['repo_name']}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )

        # Determine if this is an error case
        is_error = "error" in drift_result["plan_output"].lower() or "failed" in drift_result["plan_output"].lower()
        
        plans_table.put_item(
            Item={
                "plan_id": plan_id,
                "repo_name": config["repo_name"],
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "drift_detected": is_error or drift_result["drift_detected"],  # Show error as drift
                "changes_detected": drift_result["changes_count"],
                "plan_content": drift_result["plan_output"],
                "status": "error" if is_error else ("drift" if drift_result["drift_detected"] else "no_drift"),
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
                ),
            }
        )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {
                    "message": "Manual scan completed",
                    "plan_id": plan_id,
                    "drift_detected": drift_result["drift_detected"],
                    "changes_detected": drift_result["changes_count"],
                },
                default=decimal_default,
            ),
        }

    except Exception as e:
        logger.error(f"Error running manual scan: {str(e)}")
        return error_response(f"Failed to run manual scan: {str(e)}")


def update_drift_config(event):
    """Update drift monitoring configuration"""
    try:
        # Secure user ID and config ID handling
        user_id = str(event["user_info"]["user_id"]).strip()
        import re

        user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:50]
        if not user_id:
            return error_response("Invalid user ID", 401)

        config_id = event.get("pathParameters", {}).get("config_id")
        if config_id:
            config_id = str(config_id).strip()[:200]
            if not re.match(r"^[a-zA-Z0-9_#%-]+$", config_id):
                return error_response("Invalid config ID format", 400)

        if not config_id:
            return error_response("Missing config_id parameter", 400)

        import urllib.parse

        config_id = urllib.parse.unquote(config_id)

        body_str = event.get("body") or "{}"
        body = json.loads(body_str) if body_str else {}

        # Secure input validation
        schedule = str(body.get("schedule", "daily")).strip().lower()
        if schedule not in ["daily", "hourly"]:
            return error_response("Invalid schedule. Must be 'daily' or 'hourly'")

        alert_email = (
            str(body.get("alert_email", "")).strip()
            if body.get("alert_email")
            else None
        )
        if alert_email:
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, alert_email) or len(alert_email) > 100:
                return error_response("Invalid email format")

        drift_table_name = os.environ.get(
            "DRIFT_CONFIG_TABLE", "cloudops-assistant-drift-config"
        )
        table = dynamodb.Table(drift_table_name)
        response = table.get_item(Key={"config_id": config_id})

        if "Item" not in response or response["Item"].get("user_id") != user_id:
            return error_response("Configuration not found or unauthorized", 404)

        table.update_item(
            Key={"config_id": config_id},
            UpdateExpression="SET schedule = :schedule, alert_email = :email, updated_at = :updated",
            ExpressionAttributeValues={
                ":schedule": schedule,
                ":email": alert_email,
                ":updated": datetime.now(timezone.utc).isoformat(),
            },
        )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {
                    "message": "Configuration updated successfully",
                    "config_id": config_id,
                    "schedule": schedule,
                    "alert_email": alert_email,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error updating drift config: {str(e)}")
        return error_response("Failed to update configuration")


def delete_drift_config(event):
    """Delete drift monitoring configuration"""
    try:
        # Secure user ID and config ID handling
        user_id = str(event["user_info"]["user_id"]).strip()
        import re

        user_id = re.sub(r"[^a-zA-Z0-9_-]", "", user_id)[:50]
        if not user_id:
            return error_response("Invalid user ID", 401)

        config_id = event.get("pathParameters", {}).get("config_id")
        if not config_id:
            return error_response("Missing config_id parameter", 400)

        # URL decode and sanitize config_id
        import urllib.parse

        config_id = urllib.parse.unquote(str(config_id))
        sanitized_config_id = str(config_id).strip()[:200]
        # Only allow safe characters (after URL decoding)
        if not re.match(r"^[a-zA-Z0-9_#-]+$", sanitized_config_id):
            return error_response("Invalid config ID format", 400)

        drift_table_name = os.environ.get(
            "DRIFT_CONFIG_TABLE", "cloudops-assistant-drift-config"
        )
        table = dynamodb.Table(drift_table_name)

        # Get item first to verify ownership
        response = table.get_item(Key={"config_id": sanitized_config_id})
        if "Item" not in response:
            return error_response("Configuration not found", 404)

        # Verify ownership
        if response["Item"].get("user_id") != user_id:
            return error_response("Unauthorized", 403)

        # Delete the item
        table.delete_item(Key={"config_id": sanitized_config_id})

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps({"message": "Configuration deleted successfully"}),
        }

    except Exception as e:
        logger.error(f"Error deleting drift config: {str(e)}")
        return error_response("Failed to delete configuration")


def create_alert_topic(user_id, repo_name, email):
    """Create SNS topic for drift alerts"""
    try:
        sns = boto3.client("sns")

        # Secure topic name generation
        import re

        # Sanitize inputs for SNS topic name
        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(user_id))[:20]
        safe_repo_name = re.sub(r"[^a-zA-Z0-9_-]", "", str(repo_name))[:30]
        topic_name = f"cloudops-drift-{safe_user_id}-{safe_repo_name}"
        # Ensure topic name meets SNS requirements (alphanumeric, hyphens, underscores only)
        topic_name = re.sub(r"[^a-zA-Z0-9_-]", "-", topic_name)[:256]

        # Create topic
        response = sns.create_topic(Name=topic_name)
        topic_arn = response["TopicArn"]

        # Subscribe email
        sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=email)

        return topic_arn

    except Exception as e:
        logger.error(f"Error creating alert topic: {str(e)}")
        return None


def get_cors_headers():
    """Get secure CORS headers with proper JWT support"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "Access-Control-Max-Age": "86400",  # Cache preflight for 24 hours
    }


def execute_terraform_scan(github_url, terraform_dir):
    """Execute terraform plan using containerized TerraformExecutorFunction"""
    try:
        logger.info(f"Starting terraform scan for {github_url}")
        
        # Call the containerized TerraformExecutorFunction
        lambda_client = boto3.client('lambda')
        
        payload = {
            "httpMethod": "POST",
            "body": json.dumps({
                "repo_url": github_url,
                "branch": "main",
                "terraform_dir": terraform_dir
            }),
            "headers": {
                "Authorization": "Bearer dummy-token"
            }
        }
        
        function_name = 'cloudops-assistant-TerraformExecutorFunction-ZOrfvBDWMXoz'
        
        logger.info(f"Invoking TerraformExecutorFunction: {function_name}")
        
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',
            Payload=json.dumps(payload)
        )
        
        result = json.loads(response['Payload'].read())
        
        # Check for Lambda execution errors
        if 'errorType' in result:
            error_msg = f"TerraformExecutorFunction error: {result.get('errorType', 'Unknown')} - {result.get('errorMessage', 'No details')}"
            logger.error(error_msg)
            return {
                "drift_detected": False,
                "changes_count": 0,
                "plan_output": error_msg,
            }
        
        if result.get('statusCode') == 200:
            body = json.loads(result['body'])
            
            if body.get('success'):
                plan_output = body.get('stdout', '')
                drift_detected = detect_terraform_drift(plan_output)
                changes_count = count_terraform_changes(plan_output)
                
                logger.info(f"Terraform execution successful - Drift: {drift_detected}, Changes: {changes_count}")
                
                return {
                    "drift_detected": drift_detected,
                    "changes_count": changes_count,
                    "plan_output": plan_output,
                }
            else:
                error_msg = body.get('stderr', 'Unknown terraform error')
                logger.error(f"Terraform execution failed: {error_msg}")
                return {
                    "drift_detected": False,
                    "changes_count": 0,
                    "plan_output": f"Terraform execution failed: {error_msg}",
                }
        else:
            error_msg = result.get('body', f"HTTP {result.get('statusCode', 'Unknown')}")
            logger.error(f"TerraformExecutorFunction failed: {error_msg}")
            return {
                "drift_detected": False,
                "changes_count": 0,
                "plan_output": f"Lambda execution failed: {error_msg}",
            }
            
    except Exception as e:
        logger.error(f"Error calling TerraformExecutorFunction: {str(e)}")
        return {
            "drift_detected": False,
            "changes_count": 0,
            "plan_output": f"Failed to execute terraform scan: {str(e)}",
        }





def detect_terraform_drift(plan_output):
    """Detect if terraform plan contains drift using robust detection"""
    if not plan_output:
        return False

    # Method 1: Check for explicit "No changes" message
    if "No changes" in plan_output and "infrastructure matches" in plan_output:
        return False

    # Method 2: Parse Plan summary line (most reliable)
    import re

    clean_content = re.sub(r"\x1b\[[0-9;]*m", "", plan_output)
    plan_summary_match = re.search(
        r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy",
        clean_content,
    )
    if plan_summary_match:
        add_count = int(plan_summary_match.group(1))
        change_count = int(plan_summary_match.group(2))
        destroy_count = int(plan_summary_match.group(3))
        total_changes = add_count + change_count + destroy_count
        return total_changes > 0

    # Method 3: Look for resource action indicators
    lines = plan_output.split("\n")
    for line in lines:
        # Remove ANSI codes for cleaner matching
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)

        if (
            "will be created" in clean_line
            or "will be updated in-place" in clean_line
            or "will be destroyed" in clean_line
            or "must be replaced" in clean_line
        ):
            return True

    # Method 4: Fallback - look for any terraform action symbols
    action_indicators = ["~", "+", "-", "-/+"]
    for line in lines:
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if any(
            clean_line.startswith(f"  {indicator} ") for indicator in action_indicators
        ):
            return True

    return False


def count_terraform_changes(plan_output):
    """Count the number of changes in terraform plan output using robust detection"""
    if not plan_output:
        return 0

    # Method 1: Parse Plan summary (most reliable)
    import re

    clean_content = re.sub(r"\x1b\[[0-9;]*m", "", plan_output)
    plan_summary_match = re.search(
        r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy",
        clean_content,
    )
    if plan_summary_match:
        add_count = int(plan_summary_match.group(1))
        change_count = int(plan_summary_match.group(2))
        destroy_count = int(plan_summary_match.group(3))
        return add_count + change_count + destroy_count

    # Method 2: Count resource action lines (fallback)
    changes = 0
    lines = plan_output.split("\n")

    for line in lines:
        # Remove ANSI codes for cleaner matching
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)

        if (
            "will be created" in clean_line
            or "will be updated in-place" in clean_line
            or "will be destroyed" in clean_line
            or "must be replaced" in clean_line
        ):
            changes += 1

    return changes


def decimal_default(obj):
    """JSON serializer for DynamoDB Decimal objects"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(
        f"Object of type {type(obj).__name__} is not JSON serializable: {obj}"
    )


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }
