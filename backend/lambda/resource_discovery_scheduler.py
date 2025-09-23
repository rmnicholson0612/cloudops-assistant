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

        # Use batch processing for better performance
        if users_with_daily_scans:
            scan_results = trigger_batch_scans(users_with_daily_scans)
        else:
            scan_results = []
            logger.info("No users configured for daily scans")

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


def trigger_batch_scans(user_configs):
    """Trigger multiple scans concurrently for better performance"""
    import concurrent.futures

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_user = {
            executor.submit(trigger_user_scan, config): config
            for config in user_configs
        }

        for future in concurrent.futures.as_completed(future_to_user):
            user_config = future_to_user[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Batch scan failed for user {user_config.get('user_id', 'unknown')}: {str(e)}"
                )
                results.append(
                    {
                        "user_id": user_config.get("user_id", "unknown"),
                        "status": "failed",
                        "error": str(e),
                    }
                )

    return results


def trigger_user_scan(user_config):
    """Trigger a resource discovery scan for a specific user"""
    try:
        # Validate and sanitize user_id to prevent NoSQL injection
        import re

        raw_user_id = user_config.get("user_id")
        if not raw_user_id or not isinstance(raw_user_id, str):
            raise ValueError("Invalid user_id in config")

        # Only allow alphanumeric characters, hyphens, and underscores
        user_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(raw_user_id)[:50])
        if not user_id:
            raise ValueError("Invalid user_id format")

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

        # Invoke the resource discovery function asynchronously
        response = lambda_client.invoke(
            FunctionName="cloudops-assistant-ResourceDiscoveryFunction",
            InvocationType="Event",
            Payload=json.dumps(scan_payload),
        )

        return {
            "user_id": user_id,
            "status": "triggered",
            "response_status": response["StatusCode"],
        }

    except Exception as e:
        logger.error(
            f"Error triggering scan for user {user_config.get('user_id', 'unknown')}: {str(e)}"
        )
        raise


def store_scheduled_scan_result(user_id, scan_result):
    """Store the result of a scheduled scan"""
    try:
        # Validate and sanitize user_id to prevent NoSQL injection
        import re

        if not user_id or not isinstance(user_id, str):
            raise ValueError("Invalid user_id")

        # Only allow alphanumeric characters, hyphens, and underscores
        safe_user_id = re.sub(r"[^a-zA-Z0-9_-]", "", str(user_id)[:50])
        if not safe_user_id:
            raise ValueError("Invalid user_id format")

        now = datetime.now(timezone.utc)
        scan_id = f"scheduled-{safe_user_id}-{now.strftime('%Y%m%d')}"

        discovery_table.put_item(
            Item={
                "scan_id": scan_id,
                "user_id": safe_user_id,
                "timestamp": now.isoformat(),
                "scan_type": "scheduled",
                "results": scan_result,
                "ttl": int(now.timestamp() + (30 * 24 * 60 * 60)),  # 30 days
            }
        )

        logger.info(f"Stored scheduled scan result for user {safe_user_id[:20]}")

    except Exception as e:
        logger.error(f"Error storing scheduled scan result: {str(e)}")
