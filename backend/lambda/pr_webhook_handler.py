import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import get_cors_headers
except ImportError:

    def get_cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        }


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
lambda_client = boto3.client("lambda")

pr_reviews_table_name = os.environ.get(
    "PR_REVIEWS_TABLE", "cloudops-assistant-pr-reviews"
)
pr_reviews_table = dynamodb.Table(pr_reviews_table_name)

GITHUB_WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")


def lambda_handler(event, context):
    """Handle GitHub webhook events for PR reviews"""
    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    try:
        # Verify GitHub webhook signature
        if not verify_github_signature(event):
            logger.warning("Invalid GitHub webhook signature")
            return error_response("Invalid signature", 401)

        # Parse webhook payload
        body = json.loads(event.get("body", "{}"))
        github_event = event.get("headers", {}).get("X-GitHub-Event", "")

        logger.info(f"GitHub event: {github_event}")

        # Handle pull request events
        if github_event == "pull_request":
            return handle_pull_request_event(body)
        elif github_event == "ping":
            return success_response({"message": "Webhook configured successfully"})
        else:
            logger.info(f"Ignoring event type: {github_event}")
            return success_response({"message": "Event ignored"})

    except Exception as e:
        logger.error(f"Webhook handler error: {str(e)}")
        return error_response(f"Webhook processing failed: {str(e)}")


def verify_github_signature(event):
    """Verify GitHub webhook signature"""
    if not GITHUB_WEBHOOK_SECRET:
        logger.warning("No webhook secret configured, skipping signature verification")
        return True

    signature = event.get("headers", {}).get("X-Hub-Signature-256", "")
    if not signature:
        return False

    body = event.get("body", "")
    expected_signature = (
        "sha256="
        + hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(), body.encode(), hashlib.sha256
        ).hexdigest()
    )

    return hmac.compare_digest(signature, expected_signature)


def handle_pull_request_event(payload):
    """Process pull request opened/updated events"""
    try:
        action = payload.get("action", "")
        if action not in ["opened", "synchronize", "reopened"]:
            return success_response({"message": f"Ignoring PR action: {action}"})

        pr = payload.get("pull_request", {})
        repo = payload.get("repository", {})

        pr_data = {
            "repo_name": repo.get("name", ""),
            "repo_full_name": repo.get("full_name", ""),
            "pr_number": pr.get("number", 0),
            "pr_title": pr.get("title", ""),
            "pr_url": pr.get("html_url", ""),
            "author": pr.get("user", {}).get("login", ""),
            "base_branch": pr.get("base", {}).get("ref", ""),
            "head_branch": pr.get("head", {}).get("ref", ""),
            "head_sha": pr.get("head", {}).get("sha", ""),
            "action": action,
            "created_at": pr.get("created_at", ""),
            "updated_at": pr.get("updated_at", ""),
        }

        # Check if this is a terraform-related PR
        if not is_terraform_pr(pr_data):
            logger.info(f"PR {pr_data['pr_number']} is not terraform-related, skipping")
            return success_response({"message": "Non-terraform PR, skipping review"})

        # Trigger AI review asynchronously
        review_id = f"{pr_data['repo_full_name']}#{pr_data['pr_number']}#{pr_data['head_sha'][:8]}"

        # Store PR review record
        pr_reviews_table.put_item(
            Item={
                "review_id": review_id,
                "repo_name": pr_data["repo_name"],
                "repo_full_name": pr_data["repo_full_name"],
                "pr_number": pr_data["pr_number"],
                "pr_title": pr_data["pr_title"],
                "pr_url": pr_data["pr_url"],
                "author": pr_data["author"],
                "head_sha": pr_data["head_sha"],
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "ttl": int(
                    (datetime.now(timezone.utc).timestamp() + 2592000)
                ),  # 30 days
            }
        )

        # Invoke PR review analyzer asynchronously
        lambda_client.invoke(
            FunctionName=os.environ.get("PR_ANALYZER_FUNCTION", "pr-review-analyzer"),
            InvocationType="Event",  # Async
            Payload=json.dumps(
                {
                    "review_id": review_id,
                    "pr_data": pr_data,
                    "repo_token": get_repo_access_token(pr_data["repo_full_name"]),
                }
            ),
        )

        logger.info(
            f"Triggered AI review for PR {pr_data['pr_number']} in {pr_data['repo_full_name']}"
        )

        return success_response(
            {
                "message": "PR review triggered",
                "review_id": review_id,
                "pr_number": pr_data["pr_number"],
            }
        )

    except Exception as e:
        logger.error(f"Error handling PR event: {str(e)}")
        return error_response(f"Failed to process PR event: {str(e)}")


def is_terraform_pr(pr_data):
    """Check if PR contains terraform changes by examining file extensions"""
    # This will be enhanced by the analyzer to check actual changed files
    # For now, let the analyzer determine if it's infrastructure-related
    return True


def get_repo_access_token(repo_full_name):
    """Get GitHub access token for repository (placeholder)"""
    # In a real implementation, you'd store and retrieve GitHub tokens per repository
    # For now, return None - the analyzer will handle public repos
    return None


def success_response(data):
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(data, default=str),
    }


def error_response(message, status_code=400):
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
