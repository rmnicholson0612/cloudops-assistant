import json
import logging
import os
import boto3

logger = logging.getLogger()

def get_cognito_client():
    return boto3.client("cognito-idp")

def verify_jwt_token(event):
    """Extract and verify JWT token from Authorization header"""
    try:
        # Get token from Authorization header
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization") or headers.get("authorization")

        if not auth_header:
            return {"statusCode": 401, "body": json.dumps({"error": "Authorization header missing"})}

        if not auth_header.startswith("Bearer "):
            return {"statusCode": 401, "body": json.dumps({"error": "Invalid authorization format"})}

        token = auth_header.replace("Bearer ", "")

        # Local development bypass
        if (
            token == "mock-jwt-token-local-dev"
            and os.environ.get("LOCAL_DEV") == "true"
        ):  # nosec B105
            return {
                "user_id": "local-user",
                "email": "test@local.dev",
                "username": "local-user",
            }

        # Verify token with Cognito
        cognito_client = get_cognito_client()
        response = cognito_client.get_user(AccessToken=token)

        # Extract user info
        user_attributes = {
            attr["Name"]: attr["Value"] for attr in response["UserAttributes"]
        }

        return {
            "user_id": user_attributes.get("sub"),
            "email": user_attributes.get("email"),
            "username": response["Username"],
        }

    except Exception as auth_error:
        if 'NotAuthorizedException' in str(auth_error):
            return {"statusCode": 401, "body": json.dumps({"error": "Invalid or expired token"})}
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return {"statusCode": 401, "body": json.dumps({"error": "Token verification failed"})}
