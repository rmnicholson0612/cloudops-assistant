import difflib
import json
import logging
import os
import urllib.parse
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr, Key

try:
    from auth_utils import auth_required
except ImportError:
    auth_required = None

# Override auth_required for local development or if not available
if (
    os.environ.get("AWS_ENDPOINT_URL") == "http://localhost:4566"
    or auth_required is None
):

    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj)
        return super(DecimalEncoder, self).default(obj)


dynamodb = boto3.resource("dynamodb")

table_name = os.environ.get(
    "TERRAFORM_PLANS_TABLE", "cloudops-assistant-terraform-plans"
)
table = dynamodb.Table(table_name)


def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


def error_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }


def success_response(data):
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(data, cls=DecimalEncoder),
    }


def lambda_handler(event, context):
    # Handle CORS preflight BEFORE authentication
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    # Apply authentication for non-OPTIONS requests
    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        path = event.get("path", "")
        # method = event.get("httpMethod", "")

        if path.startswith("/plan-history/"):
            parts = path.split("/")
            if len(parts) < 3 or not parts[-1]:
                return error_response(400, "Repository name required")
            repo_name = parts[-1]
            user_id = event["user_info"]["user_id"]
            return get_plan_history(repo_name, user_id)
        elif path.startswith("/plan-details/"):
            # Extract plan_id from path parameters or path
            plan_id = event.get("pathParameters", {}).get("plan_id")
            if not plan_id:
                parts = path.split("/")
                if len(parts) >= 3 and parts[-1]:
                    plan_id = parts[-1]

            if not plan_id:
                return error_response(400, "Plan ID required")

            # URL decode the plan_id
            plan_id = urllib.parse.unquote(plan_id)
            user_id = event["user_info"]["user_id"]
            return get_plan_details(plan_id, user_id)
        elif path.startswith("/compare-plans/"):
            # Extract plan IDs from path parameters
            path_params = event.get("pathParameters", {})
            plan_id1 = path_params.get("plan1")
            plan_id2 = path_params.get("plan2")

            if not plan_id1 or not plan_id2:
                parts = path.split("/")
                if len(parts) >= 4:
                    plan_id1, plan_id2 = parts[-2], parts[-1]

            if not plan_id1 or not plan_id2:
                return error_response(400, "Two plan IDs required")

            # URL decode the plan IDs
            plan_id1 = urllib.parse.unquote(plan_id1)
            plan_id2 = urllib.parse.unquote(plan_id2)
            user_id = event["user_info"]["user_id"]
            return compare_plans(plan_id1, plan_id2, user_id)

        return error_response(404, "Not found")

    except Exception as e:
        logger.error(f"Lambda handler error: {str(e)}")
        return error_response(500, "Internal server error")


def get_plan_history(repo_name, user_id):
    try:
        response = table.query(
            IndexName="repo-timestamp-index",
            KeyConditionExpression=Key("repo_name").eq(repo_name),
            FilterExpression=Attr("user_id").eq(user_id),
            ScanIndexForward=False,  # Sort by timestamp descending (newest first)
            Limit=20,
        )

        plans = []
        for item in response["Items"]:
            plans.append(
                {
                    "plan_id": item["plan_id"],
                    "timestamp": item["timestamp"],
                    "changes_detected": item.get("changes_detected", 0),
                    "change_summary": item.get("change_summary", []),
                }
            )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {"repo_name": repo_name, "plans": plans, "total": len(plans)},
                cls=DecimalEncoder,
            ),
        }

    except Exception as e:
        logger.error(f"Failed to get plan history: {str(e)}")
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": "Failed to get history"}),
        }


def compare_plans(plan_id1, plan_id2, user_id):
    try:
        # Sanitize plan IDs to prevent NoSQL injection
        if not isinstance(plan_id1, str) or not isinstance(plan_id2, str):
            raise ValueError("Invalid plan ID format")

        response1 = table.get_item(Key={"plan_id": str(plan_id1)})
        response2 = table.get_item(Key={"plan_id": str(plan_id2)})

        # Verify user owns both plans
        if "Item" in response1 and response1["Item"].get("user_id") != user_id:
            return {
                "statusCode": 403,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Access denied"}),
            }

        if "Item" in response2 and response2["Item"].get("user_id") != user_id:
            return {
                "statusCode": 403,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Access denied"}),
            }

        if "Item" not in response1:
            return {
                "statusCode": 404,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "First plan not found"}),
            }

        if "Item" not in response2:
            return {
                "statusCode": 404,
                "headers": get_cors_headers(),
                "body": json.dumps({"error": "Second plan not found"}),
            }

        plan1 = response1["Item"]
        plan2 = response2["Item"]

        content1 = plan1.get("plan_content", "").split("\n")
        content2 = plan2.get("plan_content", "").split("\n")

        diff = list(
            difflib.unified_diff(
                content1,
                content2,
                fromfile=f"Plan {plan1['timestamp']}",
                tofile=f"Plan {plan2['timestamp']}",
                lineterm="",
            )
        )

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(
                {
                    "plan1": {
                        "id": plan_id1,
                        "timestamp": plan1["timestamp"],
                        "changes": plan1.get("changes_detected", 0),
                    },
                    "plan2": {
                        "id": plan_id2,
                        "timestamp": plan2["timestamp"],
                        "changes": plan2.get("changes_detected", 0),
                    },
                    "diff": diff[:100],  # Limit diff size
                },
                cls=DecimalEncoder,
            ),
        }

    except Exception as e:
        logger.error(f"Failed to compare plans: {str(e)}")
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": "Failed to compare plans"}),
        }


def get_plan_details(plan_id, user_id):
    try:
        if not isinstance(plan_id, str):
            raise ValueError("Invalid plan ID format")

        response = table.get_item(Key={"plan_id": str(plan_id)})

        if "Item" not in response:
            return error_response(404, "Plan not found")

        if response["Item"].get("user_id") != user_id:
            return error_response(403, "Access denied")

        plan = response["Item"]
        return success_response(
            {
                "plan_id": plan["plan_id"],
                "repo_name": plan["repo_name"],
                "timestamp": plan["timestamp"],
                "changes_detected": plan.get("changes_detected", 0),
                "drift_detected": plan.get("drift_detected", False),
                "plan_content": plan.get("plan_content", ""),
                "change_summary": plan.get("change_summary", []),
                "ai_explanation": plan.get("ai_explanation"),
                "ai_analyzed_at": plan.get("ai_analyzed_at"),
            }
        )

    except Exception as e:
        logger.error(f"Failed to get plan details: {str(e)}")
        return error_response(500, "Failed to get plan details")
