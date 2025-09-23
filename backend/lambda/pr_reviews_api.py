import json
import logging
import os

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
cognito = boto3.client("cognito-idp")

# Environment variables
PR_REVIEWS_TABLE = os.environ["PR_REVIEWS_TABLE"]
USER_POOL_ID = os.environ["USER_POOL_ID"]


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


def get_user_from_token(token):
    try:
        response = cognito.get_user(AccessToken=token)
        return response["Username"]
    except ClientError as e:
        logger.error(f"Error getting user: {e}")
        return None


def format_ai_review(ai_review):
    """Format AI review like ChatGPT output"""
    if not isinstance(ai_review, dict):
        return str(ai_review)

    # Generate ChatGPT-style review
    review_parts = []

    # Overview
    review_parts.append("# Pull Request Analysis\n")

    # Risk assessment intro
    risk_level = ai_review.get("risk_level", "MEDIUM")
    if risk_level == "LOW":
        review_parts.append(
            "I've reviewed the changes in this PR and overall they look good with minimal risk. Here's my detailed analysis:\n"
        )
    elif risk_level == "HIGH":
        review_parts.append(
            "I've identified some significant concerns in this PR that should be addressed before merging. Here's my detailed analysis:\n"
        )
    else:
        review_parts.append(
            "I've reviewed the changes in this PR and found some areas that could use attention. Here's my detailed analysis:\n"
        )

    # Security Analysis
    security_issues = ai_review.get("security_issues", [])
    if security_issues:
        review_parts.append("## 🔒 Security Concerns\n")
        review_parts.append(
            "I found the following security issues that need attention:\n"
        )
        for i, issue in enumerate(security_issues, 1):
            review_parts.append(f"{i}. **{issue}**\n")
    else:
        review_parts.append("## ✅ Security Analysis\n")
        review_parts.append(
            "Good news! I didn't identify any obvious security vulnerabilities in these changes.\n"
        )

    # Code Quality
    violations = ai_review.get("violations", [])
    if violations:
        review_parts.append("## 📝 Code Quality Issues\n")
        review_parts.append("Here are some code quality improvements I'd suggest:\n")
        for i, violation in enumerate(violations, 1):
            review_parts.append(f"{i}. {violation}\n")

    # Recommendations
    recommendations = ai_review.get("recommendations", [])
    if recommendations:
        review_parts.append("## 💡 Recommendations\n")
        review_parts.append("To improve this PR, I'd suggest:\n")
        for i, rec in enumerate(recommendations, 1):
            review_parts.append(f"{i}. {rec}\n")

    # Summary
    if risk_level == "LOW":
        review_parts.append("## Summary\n")
        review_parts.append(
            "This PR looks solid and ready to merge. The changes are well-contained and don't introduce significant risks."
        )
    elif risk_level == "HIGH":
        review_parts.append("## Summary\n")
        review_parts.append(
            "I'd recommend addressing the security concerns and code quality issues before merging this PR. The changes have potential impact that should be carefully reviewed."
        )
    else:
        review_parts.append("## Summary\n")
        review_parts.append(
            "This PR is generally good but would benefit from addressing the points mentioned above. Consider the recommendations to improve code quality and maintainability."
        )

    return "\n".join(review_parts)


def lambda_handler(event, context):
    logger.info(f"Event: {json.dumps(event, default=str)[:1000]}")

    # Handle CORS preflight
    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    # Get authorization token
    headers = event.get("headers", {})
    auth_header = headers.get("Authorization") or headers.get("authorization")

    if not auth_header or not auth_header.startswith("Bearer "):
        return error_response(401, "Missing or invalid authorization header")

    token = auth_header.split(" ")[1]
    user_id = get_user_from_token(token)

    if not user_id:
        return error_response(401, "Invalid token")

    try:
        table = dynamodb.Table(PR_REVIEWS_TABLE)
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if method == "GET" and (
            "review_id" in (event.get("queryStringParameters") or {})
        ):
            # Get specific PR review details via query parameter
            review_id = event["queryStringParameters"]["review_id"]

            # Validate review_id to prevent injection - must be alphanumeric with hyphens/underscores
            import re

            if not review_id or not isinstance(review_id, str):
                return error_response(400, "Invalid review ID")

            # Only allow alphanumeric characters, hyphens, and underscores (typical for review IDs)
            if not re.match(r"^[a-zA-Z0-9_-]+$", review_id) or len(review_id) > 100:
                return error_response(400, "Invalid review ID format")

            # Sanitize for logging to prevent log injection
            safe_review_id = re.sub(r"[^a-zA-Z0-9_-]", "", review_id)
            logger.info(f"Getting PR review details for: {safe_review_id}")

            try:
                response = table.get_item(Key={"review_id": review_id})
            except ClientError as e:
                logger.error(f"DynamoDB error getting review {safe_review_id}: {e}")
                return error_response(500, "Database error")

            if "Item" not in response:
                return error_response(404, "PR review not found")

            review = response["Item"]

            # Format AI review for display
            try:
                if "ai_review" in review and isinstance(review["ai_review"], dict):
                    ai_review = review["ai_review"]
                    formatted_review = format_ai_review(ai_review)
                    review["ai_review_formatted"] = formatted_review
            except Exception as e:
                logger.error(f"Error formatting AI review: {e}")
                # Continue without formatted review

            return success_response(review)

        elif method == "GET" and path.endswith("/pr-reviews"):
            # List PR reviews
            response = table.scan()
            reviews = response.get("Items", [])

            # Sort by created_at descending
            reviews.sort(key=lambda x: x.get("created_at", ""), reverse=True)

            return success_response({"reviews": reviews})

        elif method == "POST" and path.endswith("/pr-reviews/configure"):
            # Configure PR reviews (placeholder)

            return success_response({"message": "Configuration saved"})

        else:
            return error_response(404, "Endpoint not found")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return error_response(500, f"Internal server error: {str(e)}")
