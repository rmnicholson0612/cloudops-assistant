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


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level DynamoDB resource for connection reuse
dynamodb = boto3.resource("dynamodb")


def lambda_handler(event, context):
    """Manage drift monitoring configuration"""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    # Apply auth_required decorator logic manually for non-OPTIONS requests
    try:
        from auth_utils import verify_token

        token = event.get("headers", {}).get("Authorization", "").replace("Bearer ", "")
        if not token:
            return {
                "statusCode": 401,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "No token provided"}),
            }

        user_info = verify_token(token)
        if not user_info:
            return {
                "statusCode": 401,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Invalid token"}),
            }

        event["user_info"] = user_info
    except Exception as e:
        logger.error(f"Auth error: {str(e)}")
        return {
            "statusCode": 401,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": "Authentication failed"}),
        }

    try:
        method = event.get("httpMethod")
        path = event.get("path", "")

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
            return error_response("Invalid endpoint")

    except Exception as e:
        logger.error(f"Error in drift config handler: {str(e)}")
        return error_response("Internal server error")


def configure_drift_monitoring(event):
    """Configure a repository for drift monitoring"""
    try:
        body = json.loads(event.get("body", "{}"))
        user_id = str(event["user_info"]["user_id"]).replace("'", "").replace('"', "")

        # Sanitize and validate inputs
        repo_name = (
            str(body.get("repo_name", "")).strip()[:100]
            if body.get("repo_name")
            else None
        )
        github_url = (
            str(body.get("github_url", "")).strip()[:500]
            if body.get("github_url")
            else None
        )
        terraform_dir = str(body.get("terraform_dir", ".")).strip()[:100]
        schedule = str(body.get("schedule", "daily")).strip()[:20]
        alert_email = (
            str(body.get("alert_email", "")).strip()[:100]
            if body.get("alert_email")
            else None
        )

        # Validate GitHub URL format
        if github_url and not github_url.startswith("https://github.com/"):
            return error_response("Invalid GitHub URL format")

        # Validate schedule
        if schedule not in ["daily", "hourly"]:
            return error_response("Invalid schedule. Must be 'daily' or 'hourly'")

        # Validate email format if provided
        if alert_email:
            import re

            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, alert_email):
                return error_response("Invalid email format")

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
        table = dynamodb.Table("cloudops-assistant-drift-config")

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
        user_id = event["user_info"]["user_id"]

        config_table = dynamodb.Table("cloudops-assistant-drift-config")

        # Get user's drift configurations using proper parameterization

        response = config_table.query(
            IndexName="user-id-index",
            KeyConditionExpression=DynamoKey("user_id").eq(user_id),
        )

        configs = response.get("Items", [])

        # Get recent drift results
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        for config in configs:
            # Get latest scan result with parameterized query
            # Sanitize repo_name from database record
            repo_name = str(config.get("repo_name", "")).strip()
            if repo_name:
                plan_response = plans_table.query(
                    IndexName="repo-timestamp-index",
                    KeyConditionExpression=DynamoKey("repo_name").eq(repo_name),
                    ScanIndexForward=False,
                    Limit=1,
                )
            else:
                plan_response = {"Items": []}

            latest_scan = plan_response.get("Items", [])
            if latest_scan:
                config["last_scan"] = latest_scan[0]
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

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {"configurations": converted_configs, "total_repos": len(configs)}
            ),
        }

    except Exception as e:
        logger.error(f"Error getting drift status: {str(e)}")
        return error_response("Failed to get drift status")


def run_manual_scan(event):
    """Trigger manual drift scan for a repository"""
    try:
        user_id = str(event["user_info"]["user_id"]).replace("'", "").replace('"', "")
        config_id = event.get("pathParameters", {}).get("config_id")

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
        config_table = dynamodb.Table("cloudops-assistant-drift-config")
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
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")
        plan_id = (
            f"{config['repo_name']}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )

        plans_table.put_item(
            Item={
                "plan_id": plan_id,
                "repo_name": config["repo_name"],
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "drift_detected": drift_result["drift_detected"],
                "changes_detected": drift_result["changes_count"],
                "plan_content": drift_result["plan_output"],
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
        return error_response("Failed to run manual scan")


def update_drift_config(event):
    """Update drift monitoring configuration"""
    try:
        user_id = str(event["user_info"]["user_id"]).replace("'", "").replace('"', "")
        config_id = event.get("pathParameters", {}).get("config_id")

        if not config_id:
            return error_response("Missing config_id parameter", 400)

        import urllib.parse

        config_id = urllib.parse.unquote(config_id)

        body = json.loads(event.get("body", "{}"))
        schedule = str(body.get("schedule", "daily")).strip()[:20]
        alert_email = (
            str(body.get("alert_email", "")).strip()[:100]
            if body.get("alert_email")
            else None
        )

        if schedule not in ["daily", "hourly"] or (
            alert_email and "@" not in alert_email
        ):
            return error_response("Invalid schedule or email format")

        table = dynamodb.Table("cloudops-assistant-drift-config")
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
        user_id = event["user_info"]["user_id"]
        config_id = event["pathParameters"]["config_id"]

        # URL decode the config_id in case it's double-encoded
        import urllib.parse

        config_id = urllib.parse.unquote(config_id)
        sanitized_config_id = str(config_id).strip()[:100]

        table = dynamodb.Table("cloudops-assistant-drift-config")

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

        topic_name = f"cloudops-drift-{user_id}-{repo_name}"
        topic_name = topic_name.replace("@", "-").replace(".", "-")

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
    return {
        "Access-Control-Allow-Origin": os.environ.get(
            "ALLOWED_ORIGIN", "http://localhost:3000"
        ),
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


def execute_terraform_scan(github_url, terraform_dir):
    """Execute real terraform plan to detect drift"""
    try:
        logger.info(f"Starting terraform scan for {github_url}")
        with tempfile.TemporaryDirectory() as temp_dir:
            logger.info(f"Created temp directory: {temp_dir}")
            repo_dir = os.path.join(temp_dir, "repo")

            # Validate terraform_dir to prevent path traversal
            if os.path.isabs(terraform_dir) or ".." in terraform_dir:
                raise ValueError("Unsafe terraform directory path detected")

            tf_dir = os.path.join(repo_dir, terraform_dir)

            # Install terraform
            logger.info("Installing terraform...")
            install_result = install_terraform(temp_dir)
            if not install_result:
                logger.error("Failed to install terraform")
                return {
                    "drift_detected": False,
                    "changes_count": 0,
                    "plan_output": "Failed to install terraform",
                }

            terraform_bin = os.path.join(temp_dir, "terraform")
            logger.info(f"Terraform installed at: {terraform_bin}")

            # Clone repository
            logger.info(f"Cloning repository: {github_url}")
            clone_result = subprocess.run(
                ["git", "clone", "--depth", "1", github_url, repo_dir],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if clone_result.returncode != 0:
                logger.error(f"Clone failed: {clone_result.stderr}")
                return {
                    "drift_detected": False,
                    "changes_count": 0,
                    "plan_output": f"Failed to clone repository: {clone_result.stderr}",
                }

            logger.info(f"Repository cloned successfully to: {repo_dir}")

            # Check if terraform directory exists
            if not os.path.exists(tf_dir):
                logger.error(f"Terraform directory not found: {tf_dir}")
                return {
                    "drift_detected": False,
                    "changes_count": 0,
                    "plan_output": (
                        f"Terraform directory '{terraform_dir}' "
                        f"not found in repository"
                    ),
                }

            logger.info(f"Found terraform directory: {tf_dir}")

            # Initialize terraform
            logger.info("Running terraform init...")
            init_result = subprocess.run(
                [terraform_bin, "init", "-no-color"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )

            logger.info(f"Terraform init exit code: {init_result.returncode}")
            if init_result.returncode != 0:
                logger.error(f"Terraform init failed: {init_result.stderr}")
                return {
                    "drift_detected": False,
                    "changes_count": 0,
                    "plan_output": f"Terraform init failed: {init_result.stderr}",
                }

            logger.info("Terraform init successful, running plan...")

            # Run terraform plan
            plan_result = subprocess.run(
                [terraform_bin, "plan", "-no-color", "-detailed-exitcode"],
                cwd=tf_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )

            logger.info(f"Terraform plan exit code: {plan_result.returncode}")
            logger.info(
                f"Plan stdout length: "
                f"{len(plan_result.stdout) if plan_result.stdout else 0}"
            )
            logger.info(
                f"Plan stderr length: "
                f"{len(plan_result.stderr) if plan_result.stderr else 0}"
            )

            # Parse terraform plan results
            # Exit code 0: no changes, 1: error, 2: changes detected
            plan_output = plan_result.stdout or plan_result.stderr

            # Use robust drift detection (same as plan_processor)
            drift_detected = detect_terraform_drift(plan_output)
            changes_count = count_terraform_changes(plan_output)

            # Fallback to exit code if our detection fails
            if not drift_detected and plan_result.returncode == 2:
                drift_detected = True

            logger.info(f"Drift detected: {drift_detected}, Changes: {changes_count}")

            return {
                "drift_detected": drift_detected,
                "changes_count": changes_count,
                "plan_output": plan_result.stdout or plan_result.stderr,
            }

    except subprocess.TimeoutExpired:
        logger.error("Terraform scan timed out")
        return {
            "drift_detected": False,
            "changes_count": 0,
            "plan_output": "Terraform scan timed out",
        }
    except Exception as e:
        logger.error(f"Terraform scan error: {str(e)}")
        return {
            "drift_detected": False,
            "changes_count": 0,
            "plan_output": f"Scan failed: {str(e)}",
        }


def install_terraform(temp_dir):
    """Install terraform binary at runtime"""
    try:
        import urllib.request
        import zipfile

        # Download terraform binary
        tf_url = (
            "https://releases.hashicorp.com/terraform/1.6.6/"
            "terraform_1.6.6_linux_amd64.zip"
        )
        zip_path = os.path.join(temp_dir, "terraform.zip")

        # Use secure download with proper validation
        with urllib.request.urlopen(tf_url, timeout=30) as response:
            if response.getcode() != 200:
                raise ValueError(
                    f"Failed to download terraform: HTTP {response.getcode()}"
                )
            with open(zip_path, "wb") as f:
                f.write(response.read())

        # Extract terraform binary with path validation
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            # Validate that we're only extracting the terraform binary
            if "terraform" not in zip_ref.namelist():
                raise ValueError("terraform binary not found in zip")

            # Secure extraction to prevent path traversal
            for member in zip_ref.namelist():
                if member == "terraform":
                    # Validate member name to prevent path traversal
                    if os.path.isabs(member) or ".." in member:
                        raise ValueError("Unsafe zip member path detected")

                    # Extract safely using extractall with specific member
                    zip_ref.extractall(temp_dir, [member])
                    break

        # Make executable
        import stat

        terraform_bin = os.path.join(temp_dir, "terraform")
        os.chmod(
            terraform_bin,
            stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH,
        )

        return True

    except Exception as e:
        logger.error(f"Failed to install terraform: {str(e)}")
        return False


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
    raise TypeError


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }
