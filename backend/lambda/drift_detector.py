import json

def lambda_handler(event, context):
    # For Day 1 demo, we mock drift data
    mock_drift = {
        "drift": True,
        "details": [
            "~ aws_s3_bucket.my_bucket changed: versioning.enabled",
            "+ aws_ec2_instance.test_instance added"
        ]
    }
    
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
        },
        "body": json.dumps(mock_drift)
    }