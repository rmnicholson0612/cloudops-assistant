import json
import logging
import os
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import auth_required
except ImportError:

    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level DynamoDB resource for connection reuse
dynamodb = boto3.resource("dynamodb")


@auth_required
def lambda_handler(event, context):
    """Manage drift monitoring configuration"""
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    try:
        method = event.get("httpMethod")
        path = event.get("path", "")

        if method == "POST" and "/drift/configure" in path:
            return configure_drift_monitoring(event)
        elif method == "GET" and "/drift/status" in path:
            return get_drift_status(event)
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
        if alert_email and "@" not in alert_email:
            return error_response("Invalid email format")

        if not repo_name or not github_url:
            return error_response("repo_name and github_url are required")

        # Create SNS topic for alerts if email provided
        alert_topic_arn = None
        if alert_email:
            alert_topic_arn = create_alert_topic(user_id, repo_name, alert_email)

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
                }
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
        from boto3.dynamodb.conditions import Key

        response = config_table.query(
            IndexName="user-id-index", KeyConditionExpression=Key("user_id").eq(user_id)
        )

        configs = response.get("Items", [])

        # Get recent drift results
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        for config in configs:
            # Get latest scan result with parameterized query
            from boto3.dynamodb.conditions import Key

            # Sanitize repo_name from database record
            repo_name = str(config.get("repo_name", "")).strip()
            if repo_name:
                plan_response = plans_table.query(
                    IndexName="repo-timestamp-index",
                    KeyConditionExpression=Key("repo_name").eq(repo_name),
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

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {"configurations": configs, "total_repos": len(configs)}
            ),
        }

    except Exception as e:
        logger.error(f"Error getting drift status: {str(e)}")
        return error_response("Failed to get drift status")


def delete_drift_config(event):
    """Delete drift monitoring configuration"""
    try:
        user_id = event["user_info"]["user_id"]
        config_id = event["pathParameters"]["config_id"]

        # Verify ownership
        if not config_id.startswith(user_id):
            return error_response("Unauthorized", 403)

        table = dynamodb.Table("cloudops-assistant-drift-config")

        # Sanitize config_id to prevent injection
        sanitized_config_id = str(config_id).strip()[:100]
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
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }
