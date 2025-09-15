import json
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")
discovery_table = dynamodb.Table("cloudops-assistant-resource-discovery")


def lambda_handler(event, context):
    """Scheduled function to run daily resource discovery scans"""
    try:
        logger.info("Starting scheduled resource discovery scans")

        # Get all users who have enabled daily scans
        users_with_daily_scans = get_users_with_daily_scans()

        scan_results = []
        for user_config in users_with_daily_scans:
            try:
                result = trigger_user_scan(user_config)
                scan_results.append(result)
            except Exception as e:
                logger.error(
                    f"Failed to trigger scan for user {user_config['user_id']}: {str(e)}"
                )
                scan_results.append(
                    {
                        "user_id": user_config["user_id"],
                        "status": "failed",
                        "error": str(e),
                    }
                )

        logger.info(f"Completed scheduled scans for {len(scan_results)} users")

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "message": f"Triggered {len(scan_results)} scheduled scans",
                    "results": scan_results,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Scheduler error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_users_with_daily_scans():
    """Get list of users who have enabled daily resource discovery scans"""
    try:
        # In a real implementation, you would have a configuration table
        # For now, return empty list since we don't have user preferences stored

        # This would query a user preferences table like:
        # response = user_preferences_table.scan(
        #     FilterExpression=Attr('daily_resource_scan').eq(True)
        # )
        # return response.get('Items', [])

        return []

    except Exception as e:
        logger.error(f"Error getting users with daily scans: {str(e)}")
        return []


def trigger_user_scan(user_config):
    """Trigger a resource discovery scan for a specific user"""
    try:
        user_id = user_config["user_id"]

        # Create a scan request payload
        scan_payload = {
            "httpMethod": "POST",
            "path": "/discovery/scan",
            "body": json.dumps(
                {
                    "regions": user_config.get("regions", ["us-east-1"]),
                    "resource_types": user_config.get(
                        "resource_types", ["EC2", "Lambda", "RDS", "S3"]
                    ),
                }
            ),
            "user_info": {"user_id": user_id},
        }

        # Invoke the resource discovery function
        response = lambda_client.invoke(
            FunctionName="cloudops-assistant-ResourceDiscoveryFunction",
            InvocationType="Event",  # Async invocation
            Payload=json.dumps(scan_payload),
        )

        return {
            "user_id": user_id,
            "status": "triggered",
            "response_status": response["StatusCode"],
        }

    except Exception as e:
        logger.error(
            f"Error triggering scan for user {user_config['user_id']}: {str(e)}"
        )
        raise


def store_scheduled_scan_result(user_id, scan_result):
    """Store the result of a scheduled scan"""
    try:
        scan_id = f"scheduled-{user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d')}"

        discovery_table.put_item(
            Item={
                "scan_id": scan_id,
                "user_id": user_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scan_type": "scheduled",
                "results": scan_result,
                "ttl": int(
                    (datetime.now(timezone.utc).timestamp()) + (30 * 24 * 60 * 60)
                ),  # 30 days
            }
        )

        logger.info(f"Stored scheduled scan result for user {user_id}")

    except Exception as e:
        logger.error(f"Error storing scheduled scan result: {str(e)}")
