import json
import logging

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Cognito client
cognito_client = boto3.client("cognito-idp")


def lambda_handler(event, context):
    """
    Authentication handler for CloudOps Assistant
    Endpoints: /auth/login, /auth/register, /auth/verify
    """
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        # Handle CORS preflight
        if method == "OPTIONS":
            return cors_response()

        # Route to appropriate handler
        if path == "/auth/register" and method == "POST":
            return register_user(event)
        elif path == "/auth/login" and method == "POST":
            return login_user(event)
        elif path == "/auth/verify" and method == "POST":
            return verify_token(event)
        else:
            return error_response(404, "Endpoint not found")

    except Exception as e:
        logger.error(f"Auth handler error: {str(e)}")
        return error_response(500, "Internal server error")


def register_user(event):
    """Register a new user"""
    try:
        body = json.loads(event.get("body", "{}"))

        email = body.get("email", "").strip().lower()
        password = body.get("password", "")

        if not email or not password:
            return error_response(400, "Email and password required")

        # Basic email validation
        if "@" not in email or "." not in email:
            return error_response(400, "Invalid email format")

        # Validate environment variables
        user_pool_id = get_user_pool_id()
        if not user_pool_id:
            return error_response(500, "Service configuration error")

        # Register with Cognito
        cognito_client.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            TemporaryPassword=password,
            MessageAction="SUPPRESS",
        )

        # Set permanent password
        cognito_client.admin_set_user_password(
            UserPoolId=user_pool_id,
            Username=email,
            Password=password,
            Permanent=True
        )

        return success_response(
            {"message": "User registered successfully", "email": email}
        )

    except cognito_client.exceptions.UsernameExistsException:
        return error_response(400, "User already exists")
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return error_response(500, "Registration failed")


def login_user(event):
    """Login user and return JWT token"""
    try:
        body = json.loads(event.get("body", "{}"))

        email = body.get("email", "").strip().lower()
        password = body.get("password", "")

        if not email or not password:
            return error_response(400, "Email and password required")

        # Validate environment variables
        user_pool_id = get_user_pool_id()
        user_pool_client_id = get_user_pool_client_id()

        if not user_pool_id or not user_pool_client_id:
            return error_response(500, "Service configuration error")

        # Authenticate with Cognito
        response = cognito_client.admin_initiate_auth(
            UserPoolId=user_pool_id,
            ClientId=user_pool_client_id,
            AuthFlow="ADMIN_NO_SRP_AUTH",
            AuthParameters={"USERNAME": email, "PASSWORD": password},
        )

        # Extract tokens
        auth_result = response["AuthenticationResult"]
        access_token = auth_result["AccessToken"]
        id_token = auth_result["IdToken"]
        refresh_token = auth_result["RefreshToken"]

        return success_response(
            {
                "message": "Login successful",
                "access_token": access_token,
                "id_token": id_token,
                "refresh_token": refresh_token,
                "expires_in": auth_result["ExpiresIn"],
            }
        )

    except cognito_client.exceptions.NotAuthorizedException:
        return error_response(401, "Invalid credentials")
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return error_response(500, "Login failed")


def verify_token(event):
    """Verify JWT token"""
    try:
        body = json.loads(event.get("body", "{}"))
        token = body.get("token", "")

        if not token:
            return error_response(400, "Token required")

        # Verify token with Cognito
        response = cognito_client.get_user(AccessToken=token)

        # Extract user info
        user_attributes = {
            attr["Name"]: attr["Value"] for attr in response["UserAttributes"]
        }

        return success_response(
            {
                "valid": True,
                "username": response["Username"],
                "email": user_attributes.get("email"),
                "user_id": user_attributes.get("sub"),
            }
        )

    except cognito_client.exceptions.NotAuthorizedException:
        return error_response(401, "Invalid or expired token")
    except Exception as e:
        logger.error(f"Token verification error: {str(e)}")
        return error_response(500, "Token verification failed")


def get_user_pool_id():
    """Get User Pool ID from environment"""
    import os

    pool_id = os.environ.get("USER_POOL_ID")
    if not pool_id:
        logger.error("USER_POOL_ID environment variable not set")
    return pool_id


def get_user_pool_client_id():
    """Get User Pool Client ID from environment"""
    import os

    client_id = os.environ.get("USER_POOL_CLIENT_ID")
    if not client_id:
        logger.error("USER_POOL_CLIENT_ID environment variable not set")
    return client_id


def success_response(data):
    """Return successful API response"""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(data, default=str),
    }


def error_response(status_code, message):
    """Return error API response"""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps({"error": message}),
    }


def cors_response():
    """Return CORS preflight response"""
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": "",
    }
