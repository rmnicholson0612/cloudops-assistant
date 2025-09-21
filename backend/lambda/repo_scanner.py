import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import boto3
import urllib3

try:
    from auth_utils import auth_required
except ImportError:
    # Fallback if auth_utils not available
    def auth_required(func):
        return func


logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Module-level connections for reuse
http = urllib3.PoolManager()
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("terraform-plans")


def get_cors_headers():
    """Return CORS headers for API responses"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": (
            "Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token"
        ),
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    }


def create_error_response(message, status_code=400):
    """Create standardized error response with CORS headers"""
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message}),
    }


def sanitize_log_input(value):
    """Sanitize input for logging to prevent log injection"""
    if not isinstance(value, str):
        value = str(value)
    return re.sub(r"[\r\n\t\x00-\x1f\x7f-\x9f]", "", value)[:500]


def sanitize_db_input(value):
    """Sanitize input for database operations to prevent injection"""
    if isinstance(value, str):
        # Remove potentially dangerous characters and limit length
        sanitized = re.sub(r"[^\w\-\.@/]", "_", value)
        return sanitized[:1000]
    return value


def lambda_handler(event, context):
    # Handle CORS preflight BEFORE authentication
    if event.get("httpMethod") == "OPTIONS":
        return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

    # Apply authentication for non-OPTIONS requests
    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        body_str = event.get("body", "{}")
        if not isinstance(body_str, str):
            return create_error_response("Invalid request body format")

        body = json.loads(body_str)
        github_target = sanitize_db_input(body.get("github_target", ""))
        github_token = body.get("github_token")

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
            "body": json.dumps(
                {
                    "target": github_target,
                    "total_repos": len(repos),
                    "terraform_repos": len(terraform_repos),
                    "debug_repo_names": [
                        f"{r.get('name')} ({'private' if r.get('private') else 'public'})"
                        for r in repos[:10]
                    ],
                    "debug_info": {
                        "token_provided": bool(github_token),
                        "repo_type_used": "all" if github_token else "public",
                        "user_url": f"https://api.github.com/users/{github_target}/repos?per_page=100&type={'all' if github_token else 'public'}",
                        "org_url": f"https://api.github.com/orgs/{github_target}/repos?per_page=100&type={'all' if github_token else 'public'}",
                    },
                    "results": results,
                }
            ),
        }

    except json.JSONDecodeError as e:
        logger.error("JSON parsing error: %s", sanitize_log_input(str(e)))
        return create_error_response("Invalid JSON in request body")
    except Exception as e:
        error_msg = str(e)
        logger.error("Error scanning repos: %s", sanitize_log_input(error_msg))

        # Handle rate limiting specifically
        if "rate limit" in error_msg.lower():
            return {
                "statusCode": 429,
                "headers": get_cors_headers(),
                "body": json.dumps(
                    {
                        "error": "GitHub API rate limit exceeded",
                        "message": "Please provide a GitHub token for higher rate limits (5000/hour vs 60/hour)",
                        "suggestion": "Add a GitHub personal access token to increase your rate limit",
                    }
                ),
            }

        return create_error_response(f"Failed to scan repositories: {error_msg}")


def discover_repos(github_target, token=None):
    """Discover repos for user or org"""
    logger.info(f"Discovering repos for target: {github_target}")
    logger.info(f"Token provided: {'Yes' if token else 'No'}")
    logger.info(f"Using repo type: {'all' if token else 'public'}")

    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
        logger.info("Using GitHub token for authentication")
    else:
        logger.info(
            "No GitHub token provided - using public API (60 requests/hour limit)"
        )

    # Try authenticated user endpoint first if token provided, then public endpoints
    repo_type = "all" if token else "public"
    auth_user_url = (
        f"https://api.github.com/user/repos?per_page=100&type={repo_type}"
        if token
        else None
    )
    user_url = f"https://api.github.com/users/{github_target}/repos?per_page=100&type={repo_type}"
    org_url = f"https://api.github.com/orgs/{github_target}/repos?per_page=100&type={repo_type}"

    try:
        # If token provided, try authenticated user endpoint first (gets private repos)
        if auth_user_url:
            logger.info(f"Trying authenticated user endpoint: {auth_user_url}")
            result = _fetch_repos(auth_user_url, headers)
            if result:
                # Filter repos by owner to match target
                filtered_result = [
                    repo
                    for repo in result
                    if repo.get("owner", {}).get("login") == github_target
                ]
                if filtered_result:
                    logger.info(
                        f"Successfully found {len(filtered_result)} repos from authenticated endpoint"
                    )
                    return filtered_result

        # Try public user endpoint
        logger.info(f"Trying user endpoint: {user_url}")
        result = _fetch_repos(user_url, headers)
        if result:
            logger.info(f"Successfully found {len(result)} repos from user endpoint")
            return result

        # If user endpoint fails, try org endpoint
        logger.info(f"Trying org endpoint: {org_url}")
        result = _fetch_repos(org_url, headers)
        if result:
            logger.info(f"Successfully found {len(result)} repos from org endpoint")
            return result

    except Exception as e:
        if "rate limit" in str(e):
            logger.error("Rate limit exceeded. Please wait or provide a GitHub token.")
            raise Exception(
                "GitHub API rate limit exceeded. Please provide a GitHub token for higher limits (5000/hour vs 60/hour)."
            )
        raise e

    logger.warning("No repositories found for target")
    return []


def _fetch_repos(url, headers):
    """Fetch repositories from a single endpoint"""
    try:
        logger.info(f"Fetching repos from: {url}")
        logger.info(f"Headers: {dict(headers)}")
        response = http.request("GET", url, headers=headers, timeout=10)
        logger.info(f"Response status: {response.status}")
        logger.info(f"Response headers: {dict(response.headers)}")

        if response.status == 200:
            repos = json.loads(response.data.decode("utf-8"))
            logger.info(f"Found {len(repos)} repositories")
            # Debug: Log first few repo names and visibility
            for i, repo in enumerate(repos[:5]):
                logger.info(
                    f"Repo {i+1}: {repo.get('name')} (private: {repo.get('private', False)})"
                )
            return repos
        elif response.status == 403:
            error_data = response.data.decode("utf-8")
            logger.warning(f"403 Response body: {error_data[:500]}")
            if "rate limit" in error_data.lower():
                logger.error(
                    "GitHub API rate limit exceeded. Please add a GitHub token for higher limits."
                )
                raise Exception(
                    "GitHub API rate limit exceeded. Please provide a GitHub token."
                )
            else:
                logger.warning(f"GitHub API access denied: {error_data[:200]}")
        elif response.status == 404:
            logger.info(f"GitHub user/org not found at {url}")
        else:
            error_data = response.data.decode("utf-8")
            logger.warning(
                f"API request failed with status {response.status}: {error_data[:500]}"
            )
            logger.warning(f"Full response headers: {dict(response.headers)}")
    except Exception as e:
        if "rate limit" in str(e):
            raise  # Re-raise rate limit errors
        logger.error(f"Error fetching repos from {url}: {str(e)}")
    return None


def filter_terraform_repos(repos, token=None):
    """Filter repos that contain terraform files"""
    terraform_repos = []
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"

    # Terraform detection patterns (defined but not used in this function)

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
                logger.warning(
                    "Error checking repo %s: %s",
                    sanitize_log_input(repo.get("name", "unknown")),
                    sanitize_log_input(str(e)),
                )

    return terraform_repos


def _check_repo_terraform(repo, headers):
    """Check if a single repo contains terraform files"""
    try:
        # First check repo name/description for terraform keywords (faster)
        repo_name = repo.get("name", "").lower()
        repo_desc = (
            repo.get("description", "").lower() if repo.get("description") else ""
        )

        # Quick heuristic check first
        terraform_keywords = ["terraform", "infra", "infrastructure", "iac"]
        if any(
            keyword in repo_name or keyword in repo_desc
            for keyword in terraform_keywords
        ):
            return True

        # Only make API call if heuristic doesn't match
        url = f"https://api.github.com/repos/{repo['full_name']}/contents"
        response = http.request("GET", url, headers=headers, timeout=5)

        if response.status == 200:
            contents = json.loads(response.data.decode("utf-8"))
            # Check only first 20 files for performance
            for i, file in enumerate(contents[:20]):
                if isinstance(file, dict):
                    name_lower = file["name"].lower()
                    if (
                        ".tf" in name_lower
                        or "terraform" in name_lower
                        or "infrastructure" in name_lower
                        or "infra" in name_lower
                    ):
                        return True
            return False
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
                logger.error(
                    "Error scanning repo %s: %s",
                    sanitize_log_input(repo.get("name", "unknown")),
                    sanitize_log_input(str(e)),
                )

    return results


def scan_repo_drift(repo, token=None):
    """Real terraform drift scanning by cloning and running terraform plan"""
    import os
    import subprocess
    import tempfile

    repo_name = sanitize_db_input(repo.get("name", "unknown"))
    clone_url = repo.get("clone_url", "")

    if not clone_url:
        return {
            "repo_name": repo_name,
            "repo_url": repo.get("html_url", ""),
            "full_name": sanitize_db_input(repo.get("full_name", "")),
            "drift_detected": False,
            "changes": [],
            "last_scan": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "error": "No clone URL available",
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Clone repository
            clone_cmd = ["git", "clone", "--depth", "1", clone_url, temp_dir]
            subprocess.run(clone_cmd, check=True, capture_output=True, timeout=30)

            # Find terraform files efficiently - limit depth and check common paths
            tf_dirs = []
            common_tf_paths = [
                temp_dir,
                os.path.join(temp_dir, "terraform"),
                os.path.join(temp_dir, "infra"),
                os.path.join(temp_dir, "infrastructure"),
            ]

            # Check common paths first
            for path in common_tf_paths:
                if os.path.exists(path) and any(
                    f.endswith(".tf")
                    for f in os.listdir(path)
                    if os.path.isfile(os.path.join(path, f))
                ):
                    tf_dirs.append(path)

            # If no terraform files found in common paths, do limited walk
            if not tf_dirs:
                for root, dirs, files in os.walk(temp_dir):
                    # Limit depth to 2 levels for performance
                    level = root.replace(temp_dir, "").count(os.sep)
                    if level >= 2:
                        dirs[:] = []  # Don't recurse deeper
                    if any(f.endswith(".tf") for f in files):
                        tf_dirs.append(root)
                        if len(tf_dirs) >= 3:  # Limit to first 3 terraform directories
                            break

            if not tf_dirs:
                return {
                    "repo_name": repo_name,
                    "repo_url": repo.get("html_url", ""),
                    "full_name": sanitize_db_input(repo.get("full_name", "")),
                    "drift_detected": False,
                    "changes": [],
                    "last_scan": datetime.now(timezone.utc).isoformat(),
                    "status": "no_terraform",
                }

            # Run terraform plan in first terraform directory
            tf_dir = tf_dirs[0]
            # Validate path to prevent directory traversal
            if not os.path.commonpath([temp_dir, tf_dir]) == temp_dir:
                raise ValueError("Invalid terraform directory path")

            # Initialize terraform
            init_result = subprocess.run(
                ["terraform", "init"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tf_dir,
                env={"PATH": os.environ.get("PATH", "")},
            )
            if init_result.returncode != 0:
                return {
                    "repo_name": repo_name,
                    "repo_url": repo.get("html_url", ""),
                    "full_name": sanitize_db_input(repo.get("full_name", "")),
                    "drift_detected": False,
                    "changes": [],
                    "last_scan": datetime.now(timezone.utc).isoformat(),
                    "status": "init_failed",
                    "error": init_result.stderr[:500],
                }

            # Run terraform plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-no-color"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=tf_dir,
                env={"PATH": os.environ.get("PATH", "")},
            )

            # Parse plan output for changes
            changes = []
            has_drift = False

            if plan_result.returncode == 0:
                plan_output = plan_result.stdout

                # Check for "No changes" message
                if (
                    "No changes" in plan_output
                    and "infrastructure matches" in plan_output
                ):
                    has_drift = False
                else:
                    # Look for actual changes
                    for line in plan_output.split("\n"):
                        line = line.strip()
                        if (
                            "will be created" in line
                            or "will be updated" in line
                            or "will be destroyed" in line
                            or "must be replaced" in line
                        ):
                            changes.append(line[:200])  # Limit line length
                            has_drift = True
                            # Limit number of changes
                            if len(changes) >= 10:
                                break

            return {
                "repo_name": repo_name,
                "repo_url": repo.get("html_url", ""),
                "full_name": sanitize_db_input(repo.get("full_name", "")),
                "drift_detected": has_drift,
                "changes": [sanitize_db_input(change) for change in changes],
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "drift_detected" if has_drift else "no_drift",
                "terraform_dirs": len(tf_dirs),
            }

        except subprocess.TimeoutExpired:
            return {
                "repo_name": repo_name,
                "repo_url": repo.get("html_url", ""),
                "full_name": sanitize_db_input(repo.get("full_name", "")),
                "drift_detected": False,
                "changes": [],
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "timeout",
            }
        except Exception as e:
            return {
                "repo_name": repo_name,
                "repo_url": repo.get("html_url", ""),
                "full_name": sanitize_db_input(repo.get("full_name", "")),
                "drift_detected": False,
                "changes": [],
                "last_scan": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "error": str(e)[:200],
            }


# Removed store_scan_results - repo scanning should not store plans
