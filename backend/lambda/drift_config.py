import json
import logging
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import auth_required
except ImportError:

    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
        user_id = event["user_info"]["user_id"]

        repo_name = body.get("repo_name")
        github_url = body.get("github_url")
        terraform_dir = body.get("terraform_dir", ".")
        schedule = body.get("schedule", "daily")  # daily, hourly
        alert_email = body.get("alert_email")

        if not repo_name or not github_url:
            return error_response("repo_name and github_url are required")

        # Create SNS topic for alerts if email provided
        alert_topic_arn = None
        if alert_email:
            alert_topic_arn = create_alert_topic(user_id, repo_name, alert_email)

        # Store configuration
        dynamodb = boto3.resource("dynamodb")
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

        dynamodb = boto3.resource("dynamodb")
        config_table = dynamodb.Table("cloudops-assistant-drift-config")

        # Get user's drift configurations
        response = config_table.scan(
            FilterExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        )

        configs = response.get("Items", [])

        # Get recent drift results
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        for config in configs:
            # Get latest scan result
            plan_response = plans_table.query(
                IndexName="repo-timestamp-index",
                KeyConditionExpression="repo_name = :repo",
                ExpressionAttributeValues={":repo": config["repo_name"]},
                ScanIndexForward=False,
                Limit=1,
            )

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

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-drift-config")

        table.delete_item(Key={"config_id": config_id})

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

        topic_name = f"cloudops-drift-{user_id}-{repo_name}".replace("@", "-").replace(
            ".", "-"
        )

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
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }
