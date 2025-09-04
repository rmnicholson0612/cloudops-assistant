import json
import logging
import boto3
import re
import os
from datetime import datetime, timezone

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Compiled regex patterns for better performance
_DB_SANITIZE_PATTERN = re.compile(r'[^a-zA-Z0-9._/-]')
_LOG_SANITIZE_PATTERN = re.compile(r'[\r\n\t\x00-\x1f\x7f-\x9f]')

def get_table():
    """Get DynamoDB table with proper connection management"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('DYNAMODB_TABLE_NAME', 'cloudops-drift-results')
        return dynamodb.Table(table_name)
    except Exception as e:
        logger.error("Failed to connect to DynamoDB: %s", str(e))
        raise

def sanitize_log_input(value):
    """Sanitize input for logging to prevent log injection"""
    if not isinstance(value, str):
        value = str(value)
    return _LOG_SANITIZE_PATTERN.sub('', value)[:500]

def sanitize_db_input(value):
    """Sanitize input for database operations"""
    if isinstance(value, str):
        return _DB_SANITIZE_PATTERN.sub('', value)[:1000]
    return value

def lambda_handler(event, context):
    # Handle CORS preflight
    if event.get('httpMethod') == 'OPTIONS':
        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": ""
        }
    
    try:
        # Safer JSON parsing
        body_str = event.get('body', '{}')
        if not isinstance(body_str, str):
            return error_response("Invalid request body format")
            
        body = json.loads(body_str)
        raw_repo_name = body.get('repo_name', '')
        raw_github_target = body.get('github_target', '')
        plan_content = body.get('plan_content', '')
        
        # Validate before sanitization for better performance
        if not raw_repo_name or not raw_github_target or not plan_content:
            return error_response("repo_name, github_target, and plan_content are required")
        
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
        store_plan_result(github_target, repo_name, drift_result, plan_content)
        
        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps(drift_result)
        }
        
    except json.JSONDecodeError as e:
        logger.error("JSON parsing error: %s", sanitize_log_input(str(e)))
        return error_response("Invalid JSON in request body")
    except Exception as e:
        logger.error("Unexpected error processing plan: %s", sanitize_log_input(str(e)))
        return error_response("Failed to process terraform plan")

# Pattern matching functions for terraform plan detection
def _is_modified(line):
    return line.startswith('~') and 'resource' in line

def _is_added(line):
    return line.startswith('+') and 'resource' in line and not line.startswith('+++')

def _is_removed(line):
    return line.startswith('-') and 'resource' in line and not line.startswith('---')

def _is_created(line):
    return 'will be created' in line

def _is_updated(line):
    return 'will be updated' in line

def _is_destroyed(line):
    return 'will be destroyed' in line

def _is_summary(line):
    return 'Plan:' in line and any(x in line for x in ['to add', 'to change', 'to destroy'])

# Terraform plan patterns for change detection
_PLAN_PATTERNS = [
    (_is_modified, "Modified"),
    (_is_added, "Added"),
    (_is_removed, "Removed"),
    (_is_created, "Create"),
    (_is_updated, "Update"),
    (_is_destroyed, "Destroy"),
    (_is_summary, "Summary")
]

def process_terraform_plan(plan_content, repo_name):
    """Parse terraform plan output for changes"""
    changes = []
    has_drift = False
    
    # Early termination if we hit the change limit
    for line in plan_content.split('\n'):
        if len(changes) >= 10:  # Early termination at limit
            break
            
        stripped_line = line.strip()
        if not stripped_line:  # Skip empty lines
            continue
        
        # Check for no changes first (most common case)
        if 'No changes' in stripped_line and 'infrastructure matches' in stripped_line:
            if not has_drift:
                has_drift = False
            continue
        
        # Check patterns with early termination
        for pattern_func, change_type in _PLAN_PATTERNS:
            if pattern_func(stripped_line):
                changes.append(f"{change_type}: {stripped_line}")
                has_drift = True
                break
    
    return {
        "repo_name": sanitize_db_input(repo_name),
        "drift_detected": has_drift,
        "changes": [sanitize_db_input(change) for change in changes[:10]],  # Limit to first 10 changes
        "total_changes": len(changes),
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "status": "drift_detected" if has_drift else "no_drift",
        "scan_type": "plan_upload"
    }

def store_plan_result(github_target, repo_name, drift_result, plan_content):
    """Store plan analysis results in DynamoDB"""
    try:
        # Validate and sanitize all inputs
        if not isinstance(github_target, str) or not isinstance(repo_name, str):
            raise ValueError("Invalid input types")
            
        sanitized_target = sanitize_db_input(github_target)
        sanitized_repo = sanitize_db_input(repo_name)
        sanitized_content = sanitize_db_input(str(plan_content))
        
        # Validate sanitized inputs are not empty
        if not sanitized_target or not sanitized_repo:
            raise ValueError("Empty target or repo after sanitization")
        
        # Use single datetime call for consistency and performance
        now_utc = datetime.now(timezone.utc)
        timestamp = now_utc.isoformat()
        ttl_value = int(now_utc.timestamp()) + (30 * 24 * 60 * 60)
        
        # Store the result with validated data
        get_table().put_item(
            Item={
                'pk': sanitized_target + '#' + sanitized_repo,
                'sk': timestamp,
                'github_target': sanitized_target,
                'repo_name': sanitized_repo,
                'drift_detected': bool(drift_result.get('drift_detected', False)),
                'changes': drift_result.get('changes', [])[:10],  # Limit changes
                'total_changes': int(drift_result.get('total_changes', 0)),
                'status': str(drift_result.get('status', 'unknown')),
                'scan_type': 'plan_upload',
                'plan_content': sanitized_content[:5000],
                'ttl': ttl_value
            }
        )
        
        logger.info("Stored plan result for %s/%s", sanitize_log_input(github_target), sanitize_log_input(repo_name))
        
    except Exception as e:
        logger.error("Error storing plan result: %s", sanitize_log_input(str(e)))
        raise  # Re-raise to indicate failure

def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
    }

def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": sanitize_log_input(message)})
    }