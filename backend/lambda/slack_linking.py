import json
import logging
import os
import secrets
from datetime import datetime, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
cognito = boto3.client("cognito-idp")

# DynamoDB table
mapping_table = dynamodb.Table(
    os.environ.get("SLACK_USER_MAPPING_TABLE", "SlackUserMappingTable")
)

# Use DynamoDB for token storage with TTL


def lambda_handler(event, context):
    """Handle Slack linking requests"""
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if path == "/slack/link" and method == "GET":
            return handle_link_request(event)
        elif path == "/slack/confirm" and method == "POST":
            return handle_link_confirmation(event)

        return {
            "statusCode": 404,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": "Not found"}),
        }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": str(e)}),
        }


def handle_link_request(event):
    """Handle initial link request with token"""
    try:
        query_params = event.get("queryStringParameters") or {}
        token = query_params.get("token")

        if not token:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "text/html"},
                "body": """
                <html><body>
                <h2>❌ Invalid Link</h2>
                <p>This link is invalid or expired. Please run <code>/cloudops register</code> in Slack to get a new link.</p>
                </body></html>
                """,
            }

        # Validate token in DynamoDB
        try:
            response = mapping_table.get_item(Key={"slack_user_id": f"pending_{token}"})

            if "Item" not in response or response["Item"].get("status") != "pending":
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "text/html"},
                    "body": """
                    <html><body>
                    <h2>⏰ Link Expired</h2>
                    <p>This link has expired. Please run <code>/cloudops register</code> in Slack to get a new link.</p>
                    </body></html>
                    """,
                }
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "text/html"},
                "body": "<html><body><h2>Error</h2><p>Invalid token</p></body></html>",
            }

        # Return login form
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/html"},
            "body": (
                "<html><head><title>Link Slack to CloudOps Assistant</title>"
                "<style>body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
                "max-width: 500px; margin: 50px auto; padding: 20px; background: #f8f9fa; }}"
                ".container {{ background: white; padding: 30px; border-radius: 8px; "
                "box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}"
                ".form-group {{ margin: 20px 0; }}"
                "label {{ display: block; margin-bottom: 8px; font-weight: 600; color: #333; }}"
                "input {{ width: 100%; padding: 12px; border: 2px solid #e1e5e9; border-radius: 6px; font-size: 16px; }}"
                "input:focus {{ outline: none; border-color: #007cba; }}"
                "button {{ background: #007cba; color: white; padding: 14px 28px; border: none; "
                "border-radius: 6px; cursor: pointer; font-size: 16px; font-weight: 600; width: 100%; }}"
                "button:hover {{ background: #005a87; }}"
                "button:disabled {{ background: #ccc; cursor: not-allowed; }}"
                ".error {{ color: #d73a49; margin-top: 10px; padding: 10px; background: #ffeef0; border-radius: 4px; }}"
                ".header {{ text-align: center; margin-bottom: 30px; }}"
                ".subtitle {{ color: #666; margin-top: 10px; }}</style></head>"
                "<body><div class='container'><div class='header'>"
                "<h2>🔗 Link Your CloudOps Account</h2>"
                "<p class='subtitle'>Sign in with your existing CloudOps "
                "credentials to connect your Slack account.</p>"
                "</div><form id='linkForm'><div class='form-group'>"
                "<label for='email'>Email:</label><input type='email' id='email' name='email' required></div>"
                "<div class='form-group'><label for='password'>Password:</label>"
                "<input type='password' id='password' name='password' required></div>"
                "<button type='submit' id='submitBtn'>Link Account</button></form>"
                "<div id='error' class='error' style='display: none;'></div></div>"
                "<script>document.getElementById('linkForm').addEventListener('submit', async (e) => {{"
                "e.preventDefault(); const email = document.getElementById('email').value;"
                "const password = document.getElementById('password').value;"
                "const errorDiv = document.getElementById('error');"
                "const submitBtn = document.getElementById('submitBtn');"
                "submitBtn.disabled = true; submitBtn.textContent = 'Linking Account...';"
                "errorDiv.style.display = 'none'; try {{"
                "const response = await fetch('/Prod/slack/confirm', {{"
                "method: 'POST', headers: {{'Content-Type': 'application/json'}},"
                f"body: JSON.stringify({{ token: '{token}', email: email, password: password }})}});"
                "const result = await response.json(); if (response.ok) {{ "
                'document.body.innerHTML = \'<div class="container"><div class="header">'
                '<h2>✅ Successfully Linked!</h2><p class="subtitle">Your Slack account is now connected.</p></div>'
                '<div style="text-align: center; padding: 20px; background: #f0f8f0; border-radius: 6px; margin: 20px 0;">'
                "<p><strong>You can now use these commands in Slack:</strong></p>"
                '<ul style="text-align: left; display: inline-block;"><li><code>/cloudops status</code></li>'
                "<li><code>/cloudops costs</code></li><li><code>/cloudops drift</code></li></ul></div>"
                '<p style="text-align: center; color: #666;">You can close this window.</p></div>\';'
                "}} else {{ errorDiv.textContent = result.error || 'Login failed'; errorDiv.style.display = 'block'; }}"
                "}} catch (err) {{ errorDiv.textContent = 'Network error. Please try again.'; errorDiv.style.display = 'block'; }}"
                "finally {{ submitBtn.disabled = false; submitBtn.textContent = 'Link Account'; }} }});</script></body></html>"
            ),
        }

    except Exception as e:
        logger.error(f"Link request error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "text/html"},
            "body": f"<html><body><h2>Error</h2><p>{str(e)}</p></body></html>",
        }


def handle_link_confirmation(event):
    """Handle link confirmation with credentials"""
    try:
        body_str = event.get("body") or "{}"
        body = json.loads(body_str) if body_str else {}
        token = body.get("token")
        email = body.get("email")
        password = body.get("password")

        if not all([token, email, password]):
            return {
                "statusCode": 400,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Missing required fields"}),
            }

        # Validate token and get Slack user ID from DynamoDB
        try:
            response = mapping_table.get_item(Key={"slack_user_id": f"pending_{token}"})

            if "Item" not in response or response["Item"].get("status") != "pending":
                return {
                    "statusCode": 400,
                    "headers": get_cors_headers(),
                    "body": json.dumps({"error": "Invalid or expired token"}),
                }

            # Temporarily stored as Slack ID
            slack_user_id = response["Item"]["cognito_user_id"]

        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return {
                "statusCode": 400,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Invalid token"}),
            }

        # Authenticate with Cognito
        try:
            cognito.admin_initiate_auth(
                UserPoolId=os.environ["USER_POOL_ID"],
                ClientId=os.environ["USER_POOL_CLIENT_ID"],
                AuthFlow="ADMIN_USER_PASSWORD_AUTH",
                AuthParameters={"USERNAME": email, "PASSWORD": password},
            )

            # Get user details
            user_response = cognito.admin_get_user(
                UserPoolId=os.environ["USER_POOL_ID"], Username=email
            )

            cognito_user_id = user_response["Username"]

        except Exception as e:
            logger.error(f"Cognito auth error: {str(e)}")
            return {
                "statusCode": 401,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Invalid credentials"}),
            }

        # Store mapping
        mapping_table.put_item(
            Item={
                "slack_user_id": slack_user_id,
                "cognito_user_id": cognito_user_id,
                "email": email,
                "linked_at": datetime.now().isoformat(),
                "status": "active",
            }
        )

        # Clean up pending token
        try:
            mapping_table.delete_item(Key={"slack_user_id": f"pending_{token}"})
        except Exception as e:
            logger.error(f"Token cleanup error: {str(e)}")

        logger.info(
            "Successfully linked Slack user %s to Cognito user %s",
            slack_user_id,
            cognito_user_id,
        )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {"success": True, "message": "Account linked successfully"}
            ),
        }

    except Exception as e:
        logger.error(f"Link confirmation error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": str(e)}),
        }


def generate_link_token(slack_user_id):
    """Generate a secure token for linking"""
    token = secrets.token_urlsafe(32)
    # Store in DynamoDB instead of in-memory dict
    mapping_table.put_item(
        Item={
            "slack_user_id": f"pending_{token}",
            "cognito_user_id": slack_user_id,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "ttl": int((datetime.now() + timedelta(minutes=10)).timestamp()),
        }
    )
    return token


def get_cors_headers():
    """Get CORS headers"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": (
            "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token"
        ),
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }
