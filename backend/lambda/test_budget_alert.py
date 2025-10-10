import json
from datetime import datetime

import boto3


def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


def success_response(data):
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(data, default=str),
    }


def error_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }


def cors_response():
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": "",
    }


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    try:
        # Verify authentication using Cognito directly
        auth_header = event.get("headers", {}).get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return error_response(401, "Missing or invalid authorization header")

        token = auth_header.split(" ")[1]

        # Use Cognito to validate token and get user info
        cognito_client = boto3.client("cognito-idp")
        try:
            response = cognito_client.get_user(AccessToken=token)
            user_attributes = {
                attr["Name"]: attr["Value"] for attr in response["UserAttributes"]
            }
            user_id = user_attributes.get("sub")
            user_email = user_attributes.get("email")
        except Exception as auth_error:
            return error_response(401, f"Authentication failed: {str(auth_error)}")

        # Get test parameters from request
        body = json.loads(event.get("body", "{}"))
        test_email = body.get("email", user_email)
        budget_name = body.get("budget_name", "Test Budget Alert")
        current_spending = body.get("current_spending", 85.50)
        budget_limit = body.get("budget_limit", 100.00)
        threshold = body.get("threshold", 80)

        # Send test alert email
        sns = boto3.client("sns")

        subject = f"🚨 Budget Alert: {budget_name} - {threshold}% Threshold Exceeded"

        message = f"""
CloudOps Assistant Budget Alert

Budget: {budget_name}
Current Spending: ${current_spending:.2f}
Budget Limit: ${budget_limit:.2f}
Threshold: {threshold}%
Percentage Used: {(current_spending/budget_limit)*100:.1f}%

This is a TEST alert to verify email notifications are working.

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
User: {user_email}

CloudOps Assistant
        """.strip()

        # Create SNS topic for this test
        topic_name = f"budget-test-alert-{user_id}"

        try:
            # Create topic
            topic_response = sns.create_topic(Name=topic_name)
            topic_arn = topic_response["TopicArn"]

            # Subscribe email
            sns.subscribe(TopicArn=topic_arn, Protocol="email", Endpoint=test_email)

            # Publish test message
            publish_response = sns.publish(
                TopicArn=topic_arn, Subject=subject, Message=message
            )

            # Clean up - delete topic after sending
            sns.delete_topic(TopicArn=topic_arn)

            return success_response(
                {
                    "message": "Test budget alert sent successfully",
                    "email": test_email,
                    "message_id": publish_response.get("MessageId"),
                    "details": {
                        "budget_name": budget_name,
                        "current_spending": current_spending,
                        "budget_limit": budget_limit,
                        "threshold": threshold,
                        "percentage": round((current_spending / budget_limit) * 100, 1),
                    },
                }
            )

        except Exception as sns_error:
            return error_response(500, f"Failed to send test alert: {str(sns_error)}")

    except json.JSONDecodeError:
        return error_response(400, "Invalid JSON in request body")
    except Exception as e:
        return error_response(500, f"Internal server error: {str(e)}")
