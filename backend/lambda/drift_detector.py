import json
import logging
import re

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# CORS headers constant to avoid duplication
CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
}

def sanitize_log_input(value):
    """Sanitize input for logging to prevent log injection"""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', value)[:500]

def lambda_handler(event, context):
    try:
        # For Day 0 demo, we mock drift data
        mock_drift = {
            "drift": True,
            "details": [
                "~ aws_s3_bucket.my_bucket changed: versioning.enabled",
                "+ aws_ec2_instance.test_instance added"
            ]
        }
        
        return {
            "statusCode": 200,
            "headers": CORS_HEADERS,
            "body": json.dumps(mock_drift)
        }
    
    except Exception as e:
        logger.error("Unexpected error: %s", sanitize_log_input(str(e)))
        return {
            "statusCode": 500,
            "headers": CORS_HEADERS,
            "body": json.dumps({"error": "Internal server error"})
        }