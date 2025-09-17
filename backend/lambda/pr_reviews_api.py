import json
import logging
import os

import boto3

try:
    from auth_utils import auth_required, get_cors_headers
except ImportError:

    def auth_required(func):
        return func

    def get_cors_headers():
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        }


logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
pr_reviews_table_name = os.environ.get(
    "PR_REVIEWS_TABLE", "cloudops-assistant-pr-reviews"
)
pr_reviews_table = dynamodb.Table(pr_reviews_table_name)


def lambda_handler(event, context):
    """PR Reviews API handler"""
    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if method == "GET" and "/pr-reviews" in path:
            return get_pr_reviews(event)
        elif method == "POST" and "/pr-reviews/configure" in path:
            return configure_pr_reviews(event)
        else:
            return error_response("Invalid endpoint", 404)

    except Exception as e:
        logger.error(f"PR reviews API error: {str(e)}")
        return error_response(f"Internal server error: {str(e)}")


def get_pr_reviews(event):
    """Get PR reviews for dashboard"""
    try:
        # Get recent PR reviews (last 50)
        response = pr_reviews_table.scan(
            Limit=50, FilterExpression="attribute_exists(created_at)"
        )

        reviews = []
        for item in response.get("Items", []):
            reviews.append(
                {
                    "review_id": item.get("review_id", ""),
                    "repo_name": item.get("repo_name", ""),
                    "pr_number": item.get("pr_number", 0),
                    "pr_title": item.get("pr_title", ""),
                    "pr_url": item.get("pr_url", ""),
                    "author": item.get("author", ""),
                    "status": item.get("status", "pending"),
                    "risk_level": item.get("ai_review", {}).get(
                        "risk_level", "UNKNOWN"
                    ),
                    "created_at": item.get("created_at", ""),
                    "analyzed_at": item.get("analyzed_at", ""),
                }
            )

        # Sort by most recent
        reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return success_response(
            {"reviews": reviews[:20], "total": len(reviews)}  # Return top 20
        )

    except Exception as e:
        logger.error(f"Error getting PR reviews: {str(e)}")
        return error_response("Failed to get PR reviews")


def configure_pr_reviews(event):
    """Configure PR review settings for repositories"""
    try:
        body = json.loads(event.get("body", "{}"))
        user_id = event["user_info"]["user_id"]

        repo_name = body.get("repo_name", "").strip()
        github_url = body.get("github_url", "").strip()
        enabled = body.get("enabled", True)

        if not repo_name or not github_url:
            return error_response("Repository name and GitHub URL are required")

        # Store configuration (simplified - in real implementation you'd store per user)
        config_id = f"{user_id}#{repo_name}"

        # This is a placeholder - real implementation would store webhook configs
        logger.info(f"PR review configuration: {config_id}, enabled: {enabled}")

        return success_response(
            {
                "message": "PR review configuration saved",
                "repo_name": repo_name,
                "enabled": enabled,
                "webhook_url": f"{os.environ.get('API_BASE_URL', '')}/pr-webhook",
            }
        )

    except Exception as e:
        logger.error(f"Error configuring PR reviews: {str(e)}")
        return error_response("Failed to configure PR reviews")


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
