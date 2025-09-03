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
        "body": json.dumps(mock_drift)
    }
