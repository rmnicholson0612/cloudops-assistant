import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3

try:
    from auth_utils import auth_required
except ImportError:
    # Fallback if auth_utils not available
    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Compiled regex patterns for better performance
_DB_SANITIZE_PATTERN = re.compile(r"[^a-zA-Z0-9._/: -]")
_LOG_SANITIZE_PATTERN = re.compile(r"[\r\n\t\x00-\x1f\x7f-\x9f]")


def get_table():
    """Get DynamoDB table with proper connection management"""
    try:
        dynamodb = boto3.resource("dynamodb")
        return dynamodb.Table("cloudops-assistant-terraform-plans")
    except Exception as e:
        logger.error("Failed to connect to DynamoDB: %s", str(e))
        raise


def sanitize_log_input(value):
    """Sanitize input for logging to prevent log injection"""
    if not isinstance(value, str):
        value = str(value)
    return _LOG_SANITIZE_PATTERN.sub("", value)[:500]


def sanitize_db_input(value):
    """Sanitize input for database operations"""
    if isinstance(value, str):
        return _DB_SANITIZE_PATTERN.sub("", value)[:1000]
    return value


def lambda_handler(event, context):
    # Handle CORS preflight BEFORE authentication
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        # Safer JSON parsing
        body_str = event.get("body", "{}")
        if not isinstance(body_str, str):
            return error_response("Invalid request body format")

        body = json.loads(body_str)
        raw_repo_name = body.get("repo_name", "")
        raw_github_target = body.get("github_target", "")
        plan_content = body.get("plan_content", "")

        # Validate before sanitization for better performance
        if not raw_repo_name or not raw_github_target or not plan_content:
            return error_response(
                "repo_name, github_target, and plan_content are required"
            )

        # Sanitize only after validation
        repo_name = sanitize_db_input(raw_repo_name)
        github_target = sanitize_db_input(raw_github_target)

        # Validate plan_content size and basic format
        if len(plan_content) > 1000000:  # 1MB limit
            return error_response("plan_content too large")
        if not isinstance(plan_content, str):
            return error_response("plan_content must be a string")

        # Process the terraform plan
        drift_result = process_terraform_plan(plan_content, repo_name)

        # Store results in DynamoDB
        user_id = event["user_info"]["user_id"]
        store_plan_result(github_target, repo_name, drift_result, plan_content, user_id)

        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(drift_result),
        }

    except json.JSONDecodeError as e:
        logger.error("JSON parsing error: %s", sanitize_log_input(str(e)))
        return error_response("Invalid JSON in request body")
    except Exception as e:
        logger.error("Unexpected error processing plan: %s", sanitize_log_input(str(e)))
        return error_response("Failed to process terraform plan")


def process_terraform_plan(plan_content, repo_name):
    """Parse terraform plan output for changes with multiple detection methods"""

    # Method 1: Check for explicit "No changes" message
    if "No changes" in plan_content and "infrastructure matches" in plan_content:
        return {
            "repo_name": sanitize_db_input(repo_name),
            "drift_detected": False,
            "changes": [],
            "total_changes": 0,
            "last_scan": datetime.now(timezone.utc).isoformat(),
            "status": "no_drift",
            "scan_type": "plan_upload",
        }

    # Method 2: Parse Plan summary line (most reliable)
    # Remove ANSI codes first for better matching
    clean_content = re.sub(r"\x1b\[[0-9;]*m", "", plan_content)
    plan_summary_match = re.search(
        r"Plan:\s+(\d+)\s+to\s+add,\s+(\d+)\s+to\s+change,\s+(\d+)\s+to\s+destroy",
        clean_content,
    )
    if plan_summary_match:
        add_count = int(plan_summary_match.group(1))
        change_count = int(plan_summary_match.group(2))
        destroy_count = int(plan_summary_match.group(3))
        total_changes = add_count + change_count + destroy_count

        if total_changes > 0:
            changes = []
            if add_count > 0:
                changes.append(f"Add: {add_count} resources")
            if change_count > 0:
                changes.append(f"Change: {change_count} resources")
            if destroy_count > 0:
                changes.append(f"Destroy: {destroy_count} resources")

            return {
                "repo_name": sanitize_db_input(repo_name),
                "drift_detected": True,
                "changes": changes,
                "total_changes": total_changes,
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "drift_detected",
                "scan_type": "plan_upload",
            }

    # Method 3: Look for resource action indicators
    changes = []
    lines = plan_content.split("\n")

    for line in lines:
        # Remove ANSI codes for cleaner matching
        clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line)

        if "will be created" in clean_line:
            resource_match = re.search(r"#\s+([^\s]+)\s+will be created", clean_line)
            if resource_match:
                changes.append(f"Create: {resource_match.group(1)}")
        elif "will be updated in-place" in clean_line:
            resource_match = re.search(r"#\s+([^\s]+)\s+will be updated", clean_line)
            if resource_match:
                changes.append(f"Update: {resource_match.group(1)}")
        elif "will be destroyed" in clean_line:
            resource_match = re.search(r"#\s+([^\s]+)\s+will be destroyed", clean_line)
            if resource_match:
                changes.append(f"Destroy: {resource_match.group(1)}")
        elif "must be replaced" in clean_line:
            resource_match = re.search(r"#\s+([^\s]+)\s+must be replaced", clean_line)
            if resource_match:
                changes.append(f"Replace: {resource_match.group(1)}")

    # Method 4: Fallback - look for any terraform action symbols
    if not changes:
        action_indicators = ["~", "+", "-", "-/+"]
        for line in lines:
            clean_line = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
            if any(
                clean_line.startswith(f"  {indicator} ")
                for indicator in action_indicators
            ):
                changes.append("Infrastructure changes detected")
                break

    has_drift = len(changes) > 0

    return {
        "repo_name": sanitize_db_input(repo_name),
        "drift_detected": has_drift,
        "changes": [sanitize_db_input(change) for change in changes[:10]],
        "total_changes": len(changes),
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "status": "drift_detected" if has_drift else "no_drift",
        "scan_type": "plan_upload",
    }


def store_plan_result(github_target, repo_name, drift_result, plan_content, user_id):
    """Store plan analysis results in DynamoDB"""
    try:
        # Validate and sanitize all inputs
        if not isinstance(github_target, str) or not isinstance(repo_name, str):
            raise ValueError("Invalid input types")

        sanitized_target = sanitize_db_input(github_target)
        sanitized_repo = sanitize_db_input(repo_name)
        # Store full plan content without truncation
        sanitized_content = str(plan_content)

        # Validate sanitized inputs are not empty
        if not sanitized_target or not sanitized_repo:
            raise ValueError("Empty target or repo after sanitization")

        # Use single datetime call for consistency and performance
        now_utc = datetime.now(timezone.utc)
        timestamp = now_utc.isoformat()
        ttl_value = int(now_utc.timestamp()) + (30 * 24 * 60 * 60)
        plan_id = f"{sanitized_repo}#{timestamp}"

        # Store in terraform-plans table
        get_table().put_item(
            Item={
                "plan_id": plan_id,
                "user_id": user_id,
                "repo_name": sanitized_repo,
                "github_target": sanitized_target,
                "timestamp": timestamp,
                "plan_content": sanitized_content,
                "changes_detected": int(drift_result.get("total_changes", 0)),
                "change_summary": drift_result.get("changes", [])[:20],
                "drift_detected": bool(drift_result.get("drift_detected", False)),
                "ttl": ttl_value,
            }
        )

        logger.info(
            "Stored plan result for %s/%s",
            sanitize_log_input(github_target),
            sanitize_log_input(repo_name),
        )

    except Exception as e:
        logger.error("Error storing plan result: %s", sanitize_log_input(str(e)))
        raise  # Re-raise to indicate failure


def get_cors_headers():
    allowed_origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")
    return {
        "Access-Control-Allow-Origin": allowed_origin,
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": sanitize_log_input(message)}),
    }
