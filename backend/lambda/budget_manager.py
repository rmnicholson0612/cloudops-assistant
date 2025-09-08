import json
import logging
import os
import re
from datetime import datetime, timedelta
from decimal import Decimal

import boto3

try:
    from auth_utils import auth_required
except ImportError:
    # Fallback if auth_utils not available
    def auth_required(func):
        return func


# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ce_client = boto3.client("ce")
dynamodb = boto3.resource("dynamodb")
sns_client = boto3.client("sns")
budget_table = dynamodb.Table("cloudops-assistant-budget-config")
cost_cache_table = dynamodb.Table("cloudops-assistant-cost-cache")


def lambda_handler(event, context):
    """
    Budget Manager for CloudOps Assistant
    Endpoints: /budgets/configure, /budgets/status, /budgets/alerts
    """
    try:
        # Handle scheduled events (bypass auth for system events)
        if event.get("source") == "scheduled":
            return check_budgets_scheduled()

        # Handle CORS preflight BEFORE authentication
        if event.get("httpMethod") == "OPTIONS":
            return cors_response()

        # Apply authentication for API requests
        return _authenticated_handler(event, context)
    except Exception as e:
        logger.error(f"Budget manager error: {str(e)}")
        return error_response(500, "Internal server error")


@auth_required
def _authenticated_handler(event, context):
    path = event.get("path", "")
    method = event.get("httpMethod", "")

    # Route to appropriate handler
    user_id = event["user_info"]["user_id"]
    if path == "/budgets/configure" and method == "POST":
        return configure_budget(event, user_id)
    elif path == "/budgets/status":
        return get_budget_status(user_id)
    elif path == "/budgets/alerts":
        return get_budget_alerts(user_id)
    elif path.startswith("/budgets/delete/") and method == "DELETE":
        budget_id = path.split("/")[-1]
        return delete_budget(budget_id, user_id)
    else:
        return error_response(404, "Endpoint not found")


def configure_budget(event, user_id):
    """Configure budget thresholds"""
    try:
        body = json.loads(event.get("body", "{}"))

        # Validate required fields
        required_fields = ["budget_name", "monthly_limit", "thresholds"]
        for field in required_fields:
            if field not in body:
                return error_response(400, f"Missing required field: {field}")

        budget_name = sanitize_input(body["budget_name"])
        monthly_limit = float(body["monthly_limit"])
        thresholds = body["thresholds"]  # [50, 80, 100]
        email = body.get("email", "")
        service_filter = body.get("service_filter", "all")

        # Validate inputs
        if monthly_limit <= 0:
            return error_response(400, "Monthly limit must be positive")

        if not isinstance(thresholds, list) or not all(
            isinstance(t, (int, float)) for t in thresholds
        ):
            return error_response(400, "Thresholds must be a list of numbers")

        # Store budget configuration
        budget_config = {
            "budget_id": f"{user_id}_budget_{budget_name.lower().replace(' ', '_')}",
            "user_id": user_id,
            "budget_name": budget_name,
            "monthly_limit": Decimal(str(monthly_limit)),
            "thresholds": thresholds,
            "email": sanitize_input(email) if email else "",
            "service_filter": sanitize_input(service_filter),
            "created_at": datetime.now().isoformat(),
            "last_alert_sent": {},
            "enabled": True,
        }

        budget_table.put_item(Item=budget_config)

        return success_response(
            {
                "message": "Budget configured successfully",
                "budget_id": budget_config["budget_id"],
            }
        )

    except Exception as e:
        logger.error(f"Error configuring budget: {str(e)}")
        return error_response(500, "Failed to configure budget")


def get_budget_status(user_id):
    """Get current budget status vs actual spending"""
    try:
        # Get budget configurations for this user
        from boto3.dynamodb.conditions import Attr

        response = budget_table.scan(
            FilterExpression=Attr("user_id").eq(user_id),
            Limit=50,  # Limit scan results to prevent performance issues
        )
        budgets = response.get("Items", [])

        if not budgets:
            return success_response({"budgets": [], "message": "No budgets configured"})

        budget_status = []

        for budget in budgets:
            if not budget.get("enabled", True):
                continue

            # Get current month spending
            current_spending = get_current_spending(budget.get("service_filter", "all"))
            monthly_limit = float(budget["monthly_limit"])

            # Validate monthly_limit to prevent division by zero
            if monthly_limit <= 0:
                continue

            # Calculate percentages and forecasts
            days_in_month = get_days_in_current_month()
            current_day = datetime.now().day
            burn_rate = current_spending / current_day if current_day > 0 else 0
            projected_monthly = burn_rate * days_in_month

            # Check which thresholds are exceeded
            exceeded_thresholds = []
            for threshold in budget["thresholds"]:
                if (current_spending / monthly_limit * 100) >= threshold:
                    exceeded_thresholds.append(threshold)

            budget_status.append(
                {
                    "budget_id": budget["budget_id"],
                    "budget_name": budget["budget_name"],
                    "monthly_limit": monthly_limit,
                    "current_spending": round(current_spending, 2),
                    "percentage_used": round(
                        (current_spending / monthly_limit * 100), 1
                    ),
                    "projected_monthly": round(projected_monthly, 2),
                    "days_remaining": days_in_month - current_day,
                    "burn_rate_daily": round(burn_rate, 2),
                    "exceeded_thresholds": exceeded_thresholds,
                    "service_filter": budget.get("service_filter", "all"),
                    "status": (
                        "over_budget"
                        if current_spending > monthly_limit
                        else "warning" if exceeded_thresholds else "on_track"
                    ),
                }
            )

        return success_response(
            {"budgets": budget_status, "last_updated": datetime.now().isoformat()}
        )

    except Exception as e:
        logger.error(f"Error getting budget status: {str(e)}")
        return error_response(500, "Failed to get budget status")


def get_budget_alerts(user_id):
    """Get budget alert history"""
    try:
        # Get budgets with alert history for this user
        from boto3.dynamodb.conditions import Attr

        response = budget_table.scan(FilterExpression=Attr("user_id").eq(user_id))
        budgets = response.get("Items", [])

        alerts = []
        for budget in budgets:
            last_alerts = budget.get("last_alert_sent", {})
            for threshold, timestamp in last_alerts.items():
                alerts.append(
                    {
                        "budget_name": budget["budget_name"],
                        "threshold": int(threshold),
                        "alert_time": timestamp,
                        "budget_id": budget["budget_id"],
                    }
                )

        # Sort by most recent first
        alerts.sort(key=lambda x: x["alert_time"], reverse=True)

        return success_response(
            {"alerts": alerts[:50], "total_alerts": len(alerts)}  # Last 50 alerts
        )

    except Exception as e:
        logger.error(f"Error getting budget alerts: {str(e)}")
        return error_response(500, "Failed to get budget alerts")


def check_budgets_scheduled():
    """Scheduled function to check budgets and send alerts"""
    try:
        logger.info("Running scheduled budget check")

        # Get all enabled budgets
        response = budget_table.scan()
        budgets = response.get("Items", [])

        alerts_sent = 0

        for budget in budgets:
            if not budget.get("enabled", True):
                continue

            # Validate budget has required fields for security
            if not budget.get("budget_id"):
                logger.warning("Skipping budget with missing required fields")
                continue

            # Get current spending
            current_spending = get_current_spending(budget.get("service_filter", "all"))
            monthly_limit = float(budget["monthly_limit"])
            # Validate monthly_limit to prevent division by zero
            if monthly_limit <= 0:
                logger.warning("Skipping budget with invalid monthly_limit")
                continue

            percentage_used = current_spending / monthly_limit * 100

            # Check thresholds
            for threshold in budget["thresholds"]:
                if percentage_used >= threshold:
                    # Check if alert already sent for this threshold this month
                    last_alerts = budget.get("last_alert_sent", {})
                    current_month = datetime.now().strftime("%Y-%m")
                    alert_key = f"{threshold}_{current_month}"

                    if alert_key not in last_alerts:
                        # Send alert
                        send_budget_alert(
                            budget,
                            threshold,
                            current_spending,
                            monthly_limit,
                        )

                        # Update last alert sent
                        last_alerts[alert_key] = datetime.now().isoformat()
                        budget_table.update_item(
                            Key={"budget_id": budget["budget_id"]},
                            UpdateExpression="SET last_alert_sent = :alerts",
                            ExpressionAttributeValues={":alerts": last_alerts},
                        )

                        alerts_sent += 1

        return success_response(
            {
                "message": f"Budget check completed. {alerts_sent} alerts sent.",
                "alerts_sent": alerts_sent,
            }
        )

    except Exception as e:
        logger.error(f"Error in scheduled budget check: {str(e)}")
        return error_response(500, "Scheduled budget check failed")


def send_budget_alert(budget, threshold, current_spending, monthly_limit):
    """Send budget alert via SNS"""
    try:
        # Validate budget data comes from database and has required fields
        if not isinstance(budget, dict) or "budget_id" not in budget:
            logger.error("Invalid budget data for alert - missing required fields")
            return

        # Validate monthly_limit to prevent division by zero
        if monthly_limit <= 0:
            logger.error("Invalid monthly_limit for budget alert")
            return

        percentage = current_spending / monthly_limit * 100

        # Sanitize budget name for alert
        budget_name = sanitize_input(str(budget.get("budget_name", "Unknown")))
        subject = f"🚨 Budget Alert: {budget_name} - {threshold}% threshold exceeded"

        message = f"""
CloudOps Assistant Budget Alert

Budget: {budget_name}
Threshold: {threshold}%
Current Usage: {percentage:.1f}%

Monthly Limit: ${monthly_limit:.2f}
Current Spending: ${current_spending:.2f}
Remaining Budget: ${monthly_limit - current_spending:.2f}

Service Filter: {sanitize_input(str(budget.get('service_filter', 'all')))}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

View detailed cost breakdown in your CloudOps Assistant dashboard.
        """.strip()

        # Publish to SNS topic
        topic_arn = os.environ.get("BUDGET_ALERTS_TOPIC_ARN")
        if not topic_arn:
            logger.error("BUDGET_ALERTS_TOPIC_ARN environment variable not configured")
            return

        sns_client.publish(TopicArn=topic_arn, Subject=subject, Message=message)

        budget_id_safe = sanitize_input(str(budget.get("budget_id", "unknown")))[:50]
        logger.info(
            f"Budget alert sent for budget_id={budget_id_safe} - "
            f"{int(threshold)}% threshold"
        )

    except Exception as e:
        logger.error(f"Error sending budget alert: {str(e)}")


def get_current_spending(service_filter="all"):
    """Get current month spending, optionally filtered by service"""
    try:
        # Validate and sanitize service_filter to prevent injection
        if not isinstance(service_filter, str):
            service_filter = "all"

        service_filter = sanitize_input(service_filter)

        # Only allow specific service filters to prevent unauthorized access
        allowed_services = [
            "all",
            "EC2-Instance",
            "Lambda",
            "S3",
            "DynamoDB",
            "CloudFront",
            "API Gateway",
        ]
        if service_filter not in allowed_services:
            logger.warning(
                f"Unauthorized service filter attempted: "
                f"{sanitize_input(str(service_filter))}"
            )
            service_filter = "all"

        # Get current month dates
        now = datetime.now()
        start_date = now.replace(day=1).strftime("%Y-%m-%d")

        if service_filter == "all":
            # Use cached total cost if available
            cache_key = f"current_costs_{now.strftime('%Y-%m-%d-%H')}"
            cached = get_from_cache(cache_key)
            if cached:
                return cached.get("total_cost", 0)

        # Query Cost Explorer
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1)
        else:
            next_month = now.replace(month=now.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")

        query_params = {
            "TimePeriod": {"Start": start_date, "End": end_date},
            "Granularity": "MONTHLY",
            "Metrics": ["BlendedCost"],
        }

        # Add service filter if specified
        if service_filter != "all":
            query_params["Filter"] = {
                "Dimensions": {"Key": "SERVICE", "Values": [service_filter]}
            }

        response = ce_client.get_cost_and_usage(**query_params)

        total_cost = 0
        if response["ResultsByTime"]:
            total_cost = float(
                response["ResultsByTime"][0]["Total"]["BlendedCost"]["Amount"]
            )

        return total_cost

    except Exception as e:
        logger.error(f"Error getting current spending: {str(e)}")
        return 0


def get_days_in_current_month():
    """Get number of days in current month"""
    now = datetime.now()
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1)
    else:
        next_month = now.replace(month=now.month + 1, day=1)
    return (next_month - timedelta(days=1)).day


def get_from_cache(cache_key):
    """Get data from cost cache table with validation"""
    try:
        # Sanitize cache key to prevent NoSQL injection
        if not isinstance(cache_key, str) or len(cache_key) > 100:
            logger.warning("Invalid cache key format")
            return None

        # Only allow specific cache key patterns to prevent unauthorized access
        allowed_patterns = [
            r"^current_costs_\d{4}-\d{2}-\d{2}-\d{2}$",
            r"^cost_trends_\d{4}-\d{2}-\d{2}-\d{2}$",
        ]
        if not any(re.match(pattern, cache_key) for pattern in allowed_patterns):
            logger.warning(
                f"Unauthorized cache key pattern: {sanitize_input(str(cache_key))}"
            )
            return None

        response = cost_cache_table.get_item(Key={"cache_key": str(cache_key)})
        if "Item" in response:
            return json.loads(response["Item"]["data"])
        return None
    except Exception as e:
        logger.warning(f"Cache read error: {str(e)}")
        return None


def validate_authorization(event):
    """Validate user authorization and return user ID"""
    try:
        # Check for Authorization header
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization") or headers.get("authorization")

        if not auth_header:
            logger.warning("Missing Authorization header")
            return None

        # Validate Bearer token format
        if not auth_header.startswith("Bearer "):
            logger.warning("Invalid authorization header format")
            return None

        api_key = auth_header.replace("Bearer ", "").strip()

        # Enhanced API key validation
        if not api_key or len(api_key) < 20 or len(api_key) > 100:
            logger.warning("Invalid API key length")
            return None

        # Validate API key contains only allowed characters
        if not re.match(r"^[a-zA-Z0-9_-]+$", api_key):
            logger.warning("Invalid API key characters")
            return None

        # For demo purposes, derive user ID from API key
        # In production, validate against Cognito or JWT
        import uuid

        user_id = f"user_{str(uuid.uuid5(uuid.NAMESPACE_DNS, api_key))[:8]}"

        return user_id

    except Exception as e:
        logger.error(f"Authorization validation error: {str(e)}")
        return None


def delete_budget(budget_id, user_id):
    """Delete a budget configuration"""
    try:
        # Sanitize budget_id
        budget_id = sanitize_input(str(budget_id))

        if not budget_id:
            return error_response(400, "Invalid budget ID")

        # Validate budget exists and user owns it
        try:
            response = budget_table.get_item(Key={"budget_id": str(budget_id)})
            if "Item" not in response:
                return error_response(404, "Budget not found")
            if response["Item"].get("user_id") != user_id:
                return error_response(403, "Access denied")
        except Exception as e:
            logger.error(f"Error checking budget existence: {str(e)}")
            return error_response(500, "Failed to verify budget")

        # Delete from DynamoDB with condition to prevent race conditions
        budget_table.delete_item(
            Key={"budget_id": str(budget_id)},
            ConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        return success_response(
            {"message": "Budget deleted successfully", "budget_id": budget_id}
        )

    except Exception as e:
        logger.error(f"Error deleting budget: {str(e)}")
        return error_response(500, "Failed to delete budget")


def sanitize_input(input_str):
    """Sanitize input to prevent injection attacks"""
    if not isinstance(input_str, str):
        return str(input_str)
    # Remove potentially dangerous characters
    return re.sub(r"[^\w\-\.@/\s]", "", input_str).strip()


def success_response(data):
    """Return successful API response"""
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
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
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": json.dumps({"error": message}),
    }


def cors_response():
    """Return CORS preflight response"""
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "content-type,authorization",
            "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        },
        "body": "",
    }
