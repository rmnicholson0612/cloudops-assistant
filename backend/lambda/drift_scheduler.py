import json
import logging
from datetime import datetime, timezone

import boto3

# Import store_plan_result with error handling
try:
    from plan_processor import store_plan_result
except ImportError:

    def store_plan_result(*args, **kwargs):
        logger.warning("store_plan_result not available - using mock storage")
        return {"plan_id": f"mock_{datetime.now().isoformat()}"}


logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    """Scheduled drift monitoring - runs terraform plan on configured repos"""
    try:
        # Get configured repositories from DynamoDB
        repos = get_monitored_repos()

        results = []
        for repo_config in repos:
            try:
                # Check if repo is due for scanning based on schedule
                if not is_scan_due(repo_config):
                    continue

                result = check_repo_drift(repo_config)
                results.append(result)

                # TODO: Send email notification if drift detected or error occurred

            except Exception as e:
                logger.error(
                    "Failed to check drift for %s: %s",
                    repo_config.get("repo_name"),
                    str(e),
                )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {"message": f"Checked {len(repos)} repositories", "results": results}
            ),
        }

    except Exception as e:
        logger.error(f"Scheduler error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_monitored_repos():
    """Get list of repositories configured for drift monitoring"""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-drift-config")

        items = []
        response = table.scan()
        items.extend(response.get("Items", []))

        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

        return items

    except Exception as e:
        logger.error(f"Failed to get monitored repos: {str(e)}")
        return []


def check_repo_drift(repo_config):
    """Run terraform plan on a repository and detect drift"""
    repo_name = repo_config["repo_name"]
    github_url = repo_config["github_url"]
    terraform_dir = repo_config.get("terraform_dir", ".")

    logger.info(f"Checking drift for {repo_name}")

    try:
        # Import and use real terraform scanning
        from drift_config import execute_terraform_scan

        drift_result = execute_terraform_scan(github_url, terraform_dir)

        # Store result in DynamoDB
        dynamodb = boto3.resource("dynamodb")
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        from datetime import timedelta

        plan_id = (
            f"{repo_name}-scheduled-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )

        plans_table.put_item(
            Item={
                "plan_id": plan_id,
                "repo_name": repo_name,
                "user_id": repo_config["user_id"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "drift_detected": drift_result["drift_detected"],
                "changes_detected": drift_result["changes_count"],
                "plan_content": drift_result["plan_output"],
                "scan_type": "scheduled",
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=30)).timestamp()
                ),
            }
        )

        return {
            "repo_name": repo_name,
            "drift_detected": drift_result["drift_detected"],
            "changes_count": drift_result["changes_count"],
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "plan_id": plan_id,
        }

    except Exception as e:
        logger.error(f"Error checking drift for {repo_name}: {str(e)}")
        return {
            "repo_name": repo_name,
            "drift_detected": False,
            "changes_count": 0,
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
        }


def is_scan_due(repo_config):
    """Check if repository is due for scanning based on schedule"""
    try:
        schedule = repo_config.get("schedule", "daily")

        # Get last scan time from DynamoDB
        dynamodb = boto3.resource("dynamodb")
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        from boto3.dynamodb.conditions import Key

        # Sanitize and validate repo_name to prevent injection
        repo_name = str(repo_config.get("repo_name", "")).strip()

        # Strict validation for repo_name format
        import re

        if (
            not repo_name
            or not re.match(r"^[a-zA-Z0-9._-]+$", repo_name)
            or len(repo_name) > 100
        ):
            logger.warning(f"Invalid repo_name format: {repo_name}")
            return True

        # Use parameterized query with boto3.dynamodb.conditions for safe query construction
        response = plans_table.query(
            IndexName="repo-timestamp-index",
            KeyConditionExpression=Key("repo_name").eq(repo_name),
            ScanIndexForward=False,
            Limit=1,
        )

        if not response.get("Items"):
            return True  # No previous scan, scan now

        last_scan = response["Items"][0]["timestamp"]
        last_scan_time = datetime.fromisoformat(last_scan.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        # Check if enough time has passed based on schedule
        if schedule == "hourly":
            return (now - last_scan_time).total_seconds() >= 3600  # 1 hour
        elif schedule == "daily":
            return (now - last_scan_time).total_seconds() >= 86400  # 24 hours
        else:
            return (now - last_scan_time).total_seconds() >= 86400  # Default daily

    except Exception as e:
        logger.error(f"Error checking scan schedule: {str(e)}")
        return True  # Default to scanning if error


# TODO: Implement email notifications for drift alerts
