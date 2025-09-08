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


def create_error_response(message):
    """Create standardized error response with CORS headers"""
    return {
        "statusCode": 400,
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
                    "results": results,
                }
            ),
        }

    except json.JSONDecodeError as e:
        logger.error("JSON parsing error: %s", sanitize_log_input(str(e)))
        return create_error_response("Invalid JSON in request body")
    except Exception as e:
        logger.error("Error scanning repos: %s", sanitize_log_input(str(e)))
        return create_error_response("Failed to scan repositories")


def discover_repos(github_target, token=None):
    """Discover repos for user or org"""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    # Try both endpoints in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        user_future = executor.submit(
            _fetch_repos,
            f"https://api.github.com/users/{github_target}/repos?per_page=100",
            headers,
        )
        org_future = executor.submit(
            _fetch_repos,
            f"https://api.github.com/orgs/{github_target}/repos?per_page=100",
            headers,
        )

        # Return first successful result
        for future in as_completed([user_future, org_future]):
            result = future.result()
            if result:
                return result

    return []


def _fetch_repos(url, headers):
    """Fetch repositories from a single endpoint"""
    try:
        response = http.request("GET", url, headers=headers)
        if response.status == 200:
            return json.loads(response.data.decode("utf-8"))
    except (urllib3.exceptions.HTTPError, json.JSONDecodeError):
        pass
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

            # Find terraform files efficiently - limit depth and check common locations first
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

            # If no terraform files found in common paths, do limited walk (max 2 levels)
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
