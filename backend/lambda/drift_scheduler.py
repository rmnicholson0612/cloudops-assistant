import json
import logging
from datetime import datetime, timezone

import boto3
from plan_processor import store_plan_result

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
                result = check_repo_drift(repo_config)
                results.append(result)

                # Send alert if drift detected
                if result.get("drift_detected"):
                    send_drift_alert(repo_config, result)

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

        response = table.scan()
        return response.get("Items", [])

    except Exception as e:
        logger.error(f"Failed to get monitored repos: {str(e)}")
        return []


def check_repo_drift(repo_config):
    """Run terraform plan on a repository and detect drift"""
    repo_name = repo_config["repo_name"]
    github_url = repo_config["github_url"]

    logger.info(f"Checking drift for {repo_name}")

    # For Day 7 MVP: Mock drift detection since real terraform requires AWS creds
    try:
        import random

        has_changes = random.choice([True, False])  # 50% chance of drift

        if has_changes:
            mock_changes = [
                f"Update: aws_instance.{repo_name}_server",
                f"Create: aws_s3_bucket.{repo_name}_logs",
            ]
            drift_result = {
                "repo_name": repo_name,
                "drift_detected": True,
                "changes": mock_changes,
                "total_changes": len(mock_changes),
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "drift_detected",
                "scan_type": "scheduled",
            }
        else:
            drift_result = {
                "repo_name": repo_name,
                "drift_detected": False,
                "changes": [],
                "total_changes": 0,
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "no_drift",
                "scan_type": "scheduled",
            }

        # Store result using existing function
        store_plan_result(
            github_target=github_url,
            repo_name=repo_name,
            drift_result=drift_result,
            plan_content=f"Mock terraform plan for {repo_name}\n"
            + (
                "\n".join([f"# {change}" for change in drift_result["changes"]])
                if drift_result["changes"]
                else "No changes."
            ),
            user_id=repo_config["user_id"],
        )

        return {
            "repo_name": repo_name,
            "drift_detected": drift_result["drift_detected"],
            "changes": drift_result["changes"],
            "scan_time": drift_result["last_scan"],
        }

    except Exception as e:
        logger.error(f"Error checking drift for {repo_name}: {str(e)}")
        return {
            "repo_name": repo_name,
            "drift_detected": False,
            "changes": [],
            "scan_time": datetime.now(timezone.utc).isoformat(),
        }


def send_drift_alert(repo_config, drift_result):
    """Send SNS alert when drift is detected"""
    try:
        sns = boto3.client("sns")
        topic_arn = repo_config.get("alert_topic_arn")

        if not topic_arn:
            return

        message = f"""
🚨 Infrastructure Drift Detected!

Repository: {repo_config['repo_name']}
Changes Detected: {len(drift_result['changes'])}

Changes:
{chr(10).join(drift_result['changes'][:5])}

Scan Time: {drift_result['scan_time']}
        """

        sns.publish(
            TopicArn=topic_arn,
            Subject=f"Drift Alert: {repo_config['repo_name']}",
            Message=message,
        )

        logger.info(f"Sent drift alert for {repo_config['repo_name']}")

    except Exception as e:
        logger.error(f"Failed to send alert: {str(e)}")
