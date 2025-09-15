import json
import logging

import boto3

logger = logging.getLogger()
cognito_client = boto3.client("cognito-idp")


def verify_jwt_token(event):
    """Extract and verify JWT token from Authorization header"""
    try:
        # Get token from Authorization header
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization") or headers.get("authorization")

        if not auth_header:
            return None, "Authorization header missing"

        if not auth_header.startswith("Bearer "):
            return None, "Invalid authorization format"

        token = auth_header.replace("Bearer ", "")

        # Verify token with Cognito
        response = cognito_client.get_user(AccessToken=token)

        # Extract user info
        user_attributes = {
            attr["Name"]: attr["Value"] for attr in response["UserAttributes"]
        }

        return {
            "user_id": user_attributes.get("sub"),
            "email": user_attributes.get("email"),
            "username": response["Username"],
        }, None

    except cognito_client.exceptions.NotAuthorizedException:
        return None, "Invalid or expired token"
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return None, "Token verification failed"


def verify_token(token):
    """Verify JWT token and return user info"""
    try:
        response = cognito_client.get_user(AccessToken=token)
        user_attributes = {
            attr["Name"]: attr["Value"] for attr in response["UserAttributes"]
        }
        return {
            "user_id": user_attributes.get("sub"),
            "email": user_attributes.get("email"),
            "username": response["Username"],
        }
    except Exception:
        return None


def auth_required(handler_func):
    """Decorator to require authentication for Lambda handlers"""

    def wrapper(event, context):
        user_info, error = verify_jwt_token(event)

        if error:
            return {
                "statusCode": 401,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                },
                "body": json.dumps({"error": error}),
            }

        # Add user info to event for handler to use
        event["user_info"] = user_info
        return handler_func(event, context)

    return wrapper
