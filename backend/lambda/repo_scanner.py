import json
import logging
import urllib3
import boto3
import re
import random
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level connections for reuse
http = urllib3.PoolManager()
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('terraform-plans')

def get_cors_headers():
    """Return CORS headers for API responses"""
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

def create_error_response(message):
    """Create standardized error response with CORS headers"""
    return {
        "statusCode": 400,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message})
    }

def sanitize_log_input(value):
    """Sanitize input for logging to prevent log injection"""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r'[\r\n\t\x00-\x1f\x7f-\x9f]', '', value)[:500]

def sanitize_db_input(value):
    """Sanitize input for database operations to prevent injection"""
    if isinstance(value, str):
        # Remove potentially dangerous characters and limit length
        sanitized = re.sub(r'[^\w\-\.@/]', '_', value)
        return sanitized[:1000]
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
        body_str = event.get('body', '{}')
        if not isinstance(body_str, str):
            return create_error_response("Invalid request body format")
            
        body = json.loads(body_str)
        github_target = sanitize_db_input(body.get('github_target', ''))
        github_token = body.get('github_token')
        
        if not github_target:
            return create_error_response("github_target is required")
        
        # Discover repositories
        repos = discover_repos(github_target, github_token)
        terraform_repos = filter_terraform_repos(repos, github_token)
        
        # Scan terraform repos for drift (with parallel processing)
        results = scan_repos_parallel(terraform_repos, github_token)
        
        return {
            "statusCode": 200,
            "headers": get_cors_headers(),
            "body": json.dumps({
                "target": github_target,
                "total_repos": len(repos),
                "terraform_repos": len(terraform_repos),
                "results": results
            })
        }
        
    except json.JSONDecodeError as e:
        logger.error("JSON parsing error: %s", sanitize_log_input(str(e)))
        return create_error_response("Invalid JSON in request body")
    except Exception as e:
        logger.error("Error scanning repos: %s", sanitize_log_input(str(e)))
        return create_error_response("Failed to scan repositories")

def discover_repos(github_target, token=None):
    """Discover repos for user or org"""
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'
    
    # Try both endpoints in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        user_future = executor.submit(_fetch_repos, f'https://api.github.com/users/{github_target}/repos?per_page=100', headers)
        org_future = executor.submit(_fetch_repos, f'https://api.github.com/orgs/{github_target}/repos?per_page=100', headers)
        
        # Return first successful result
        for future in as_completed([user_future, org_future]):
            result = future.result()
            if result:
                return result
    
    return []

def _fetch_repos(url, headers):
    """Fetch repositories from a single endpoint"""
    try:
        response = http.request('GET', url, headers=headers)
        if response.status == 200:
            return json.loads(response.data.decode('utf-8'))
    except (urllib3.exceptions.HTTPError, json.JSONDecodeError):
        pass
    return None

def filter_terraform_repos(repos, token=None):
    """Filter repos that contain terraform files"""
    terraform_repos = []
    headers = {}
    if token:
        headers['Authorization'] = f'token {token}'
    
    # Terraform detection patterns
    terraform_patterns = ['.tf', 'terraform', 'infrastructure', 'infra']
    
    # Use ThreadPoolExecutor for parallel repo filtering
    with ThreadPoolExecutor(max_workers=3) as executor:
        future_to_repo = {
            executor.submit(_check_repo_terraform, repo, headers): repo 
            for repo in repos
        }
        
        for future in as_completed(future_to_repo):
            try:
                if future.result():
                    terraform_repos.append(future_to_repo[future])
            except Exception as e:
                repo = future_to_repo[future]
                logger.warning("Error checking repo %s: %s", 
                             sanitize_log_input(repo.get('name', 'unknown')), 
                             sanitize_log_input(str(e)))
    
    return terraform_repos

def _check_repo_terraform(repo, headers):
    """Check if a single repo contains terraform files"""
    try:
        url = f"https://api.github.com/repos/{repo['full_name']}/contents"
        response = http.request('GET', url, headers=headers)
        
        if response.status == 200:
            contents = json.loads(response.data.decode('utf-8'))
            terraform_patterns = ['.tf', 'terraform', 'infrastructure', 'infra']
            return any(
                any(pattern in file['name'].lower() for pattern in terraform_patterns)
                for file in contents if isinstance(file, dict)
            )
    except (urllib3.exceptions.HTTPError, json.JSONDecodeError, KeyError):
        pass
    return False


def scan_repos_parallel(terraform_repos, github_token):
    """Scan repositories in parallel for better performance"""
    results = []
    
    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_repo = {
            executor.submit(scan_repo_drift, repo, github_token): repo 
            for repo in terraform_repos
        }
        
        for future in as_completed(future_to_repo):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                repo = future_to_repo[future]
                logger.error("Error scanning repo %s: %s", 
                           sanitize_log_input(repo.get('name', 'unknown')), 
                           sanitize_log_input(str(e)))
    
    return results

def scan_repo_drift(repo, token=None):
    """Mock terraform drift scanning for a repo"""
    # For Day 1, we'll simulate drift detection
    # In future days, this would clone repo and run terraform plan
    
    has_drift = random.choice([True, False, False])  # 33% chance of drift
    
    repo_name = sanitize_db_input(repo.get('name', 'unknown'))
    
    if has_drift:
        # Use safe string concatenation instead of f-strings for user input
        mock_changes = [
            "~ aws_s3_bucket." + repo_name + "_bucket changed: versioning.enabled",
            "+ aws_cloudwatch_log_group." + repo_name + "_logs added"
        ]
    else:
        mock_changes = []
    
    return {
        "repo_name": repo_name,
        "repo_url": repo.get('html_url', ''),
        "full_name": sanitize_db_input(repo.get('full_name', '')),
        "drift_detected": has_drift,
        "changes": [sanitize_db_input(change) for change in mock_changes],
        "last_scan": datetime.now(timezone.utc).isoformat(),
        "status": "drift_detected" if has_drift else "no_drift"
    }

# Removed store_scan_results - repo scanning should not store plans

def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS"
    }

def create_error_response(error_message):
    """Create standardized error response with CORS headers"""
    return {
        "statusCode": 400,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": sanitize_db_input(error_message)})
    }