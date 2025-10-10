import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import boto3
import requests

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

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")

eol_database_table_name = os.environ.get(
    "EOL_DATABASE_TABLE", "cloudops-assistant-eol-database-v2"
)
eol_scans_table_name = os.environ.get(
    "EOL_SCANS_TABLE", "cloudops-assistant-eol-scans-v2"
)

eol_database_table = dynamodb.Table(eol_database_table_name)
eol_scans_table = dynamodb.Table(eol_scans_table_name)


def lambda_handler(event, context):
    """EOL Tracker - Track end-of-life dates for tech stack"""
    logger.info(f"EOL Lambda handler called with method: {event.get('httpMethod')}")
    logger.info(f"Path: {event.get('path')}")

    if event.get("httpMethod") == "OPTIONS":
        return cors_response()

    return _authenticated_handler(event, context)


@auth_required
def _authenticated_handler(event, context):
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        logger.info(f"EOL Handler - Path: {path}, Method: {method}")
        logger.info(f"User info: {event.get('user_info', {})}")

        if method == "GET" and "/eol/dashboard" in path:
            return get_eol_dashboard(event)
        elif method == "POST" and "/eol/scan" in path:
            return trigger_eol_scan(event)
        elif method == "GET" and "/eol/scans" in path:
            return get_eol_scans(event)
        elif method == "GET" and "/eol/database" in path:
            return get_eol_database(event)
        elif method == "DELETE" and "/eol/cleanup" in path:
            return cleanup_user_scans(event)
        else:
            return error_response("Invalid endpoint", 404)

    except Exception as e:
        logger.error(f"EOL tracker error: {str(e)}")
        logger.error(f"Event: {json.dumps(event, default=str)}")
        return error_response(f"Internal server error: {str(e)}")


def get_eol_dashboard(event):
    """Get EOL dashboard data for user"""
    try:
        user_id = event["user_info"]["user_id"]

        # Get all scans for user and group by repo to get latest per repo
        response = eol_scans_table.query(
            IndexName="user-id-index",
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        all_scans = response.get("Items", [])

        # Group by repo_name and keep only the latest scan per repo
        latest_scans_by_repo = {}
        for scan in all_scans:
            repo_name = scan.get("repo_name")
            scan_date = scan.get("scan_date")

            if repo_name:
                if (
                    repo_name not in latest_scans_by_repo
                    or scan_date > latest_scans_by_repo[repo_name].get("scan_date")
                ):
                    latest_scans_by_repo[repo_name] = scan

        # Convert back to list and sort by scan date
        scans = list(latest_scans_by_repo.values())
        scans.sort(key=lambda x: x.get("scan_date", ""), reverse=True)

        # Aggregate findings by risk level
        risk_summary = {"critical": 0, "high": 0, "medium": 0, "low": 0, "unknown": 0}
        recent_findings = []

        for scan in scans:
            findings = scan.get("findings", [])
            for finding in findings:
                risk_level = finding.get("risk_level", "low").lower()
                if risk_level in risk_summary:
                    risk_summary[risk_level] += 1

                # Add to recent findings if high risk
                if risk_level in ["critical", "high"]:
                    recent_findings.append(
                        {
                            "technology": finding.get("technology"),
                            "version": finding.get("version"),
                            "eol_date": finding.get("eol_date"),
                            "risk_level": risk_level,
                            "repo_name": scan.get("repo_name"),
                            "scan_date": scan.get("scan_date"),
                        }
                    )

        # Sort recent findings by EOL date
        recent_findings.sort(key=lambda x: x.get("eol_date", "9999-12-31"))

        return success_response(
            {
                "risk_summary": risk_summary,
                "recent_findings": recent_findings[:20],
                "total_scans": len(scans),
                "last_scan": scans[0].get("scan_date") if scans else None,
            }
        )

    except Exception as e:
        logger.error(f"Error getting EOL dashboard: {str(e)}")
        return error_response("Failed to get EOL dashboard")


def trigger_eol_scan(event):
    """Trigger EOL scan for repositories"""
    try:
        user_id = event["user_info"]["user_id"]
        body_str = event.get("body", "{}")
        logger.info(f"Raw body: {body_str}")

        try:
            body = json.loads(body_str)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return error_response("Invalid JSON in request body")

        github_target = body.get("github_target")
        github_token = body.get("github_token")

        logger.info(f"Parsed github_target: {github_target}")
        logger.info(f"Token provided: {'Yes' if github_token else 'No'}")

        if not github_target:
            return error_response("github_target is required")

        # Scan repositories for dependency files
        repos = scan_github_repos(github_target, github_token)
        scan_results = []

        for repo in repos:  # Scan all discovered repos
            findings = scan_repo_dependencies(repo, github_token)

            # Use deterministic scan_id to prevent duplicates
            scan_id = f"{user_id}#{repo['name']}"
            scan_date = datetime.now(timezone.utc).isoformat()

            # Check for version changes by comparing with previous scan
            previous_scan = None
            try:
                prev_response = eol_scans_table.get_item(
                    Key={"scan_id": f"{user_id}#{repo['name']}"}
                )
                if "Item" in prev_response:
                    previous_scan = prev_response["Item"]
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Error retrieving previous scan: {str(e)}")
                pass
            except Exception as e:
                logger.error(f"Unexpected error retrieving previous scan: {str(e)}")
                pass

            # Track version changes and update findings
            for finding in findings:
                finding["last_seen"] = scan_date
                technology_found_in_previous = False

                # Check if this technology existed in previous scan
                if previous_scan:
                    prev_findings = previous_scan.get("findings", [])
                    for prev_finding in prev_findings:
                        if (
                            prev_finding.get("technology") == finding.get("technology")
                            and prev_finding.get("tech_type")
                            == finding.get("tech_type")
                            and prev_finding.get("file_path")
                            == finding.get("file_path")
                        ):
                            technology_found_in_previous = True

                            # Preserve first seen date from previous scan
                            finding["first_seen"] = prev_finding.get(
                                "first_seen", prev_finding.get("last_seen", scan_date)
                            )

                            prev_version = prev_finding.get("version")
                            current_version = finding.get("version")

                            if prev_version != current_version:
                                finding["version_changed"] = True
                                finding["previous_version"] = prev_version
                                finding["version_change_date"] = scan_date
                                logger.info(
                                    f"Version change detected: {finding.get('technology')} {prev_version} -> {current_version}"
                                )
                            break

                # If not found in previous scan, this is first time seeing it
                if not technology_found_in_previous:
                    finding["first_seen"] = scan_date

            scan_record = {
                "scan_id": scan_id,
                "user_id": user_id,
                "repo_name": repo["name"],
                "repo_url": repo["html_url"],
                "scan_date": scan_date,
                "findings": findings,
                "ttl": int((datetime.now() + timedelta(days=90)).timestamp()),
            }

            eol_scans_table.put_item(Item=scan_record)
            eol_risks = [
                f
                for f in findings
                if f.get("risk_level") in ["critical", "high", "medium"]
            ]
            # Count version changes
            version_changes = [f for f in findings if f.get("version_changed")]

            scan_results.append(
                {
                    "repo_name": repo["name"],
                    "technologies_count": len(findings),
                    "eol_risk_count": len(eol_risks),
                    "version_changes_count": len(version_changes),
                    "technologies": findings[:10],  # Show first 10 technologies
                    "eol_risks": eol_risks[:5],  # Show first 5 EOL risks
                    "version_changes": version_changes[
                        :3
                    ],  # Show first 3 version changes
                }
            )

        total_technologies = sum(
            len(result.get("technologies", [])) for result in scan_results
        )

        return success_response(
            {
                "scanned_repos": len(repos),
                "total_technologies": total_technologies,
                "scan_results": scan_results,
            }
        )

    except Exception as e:
        logger.error(f"Error triggering EOL scan: {str(e)}")
        logger.error(f"Event: {json.dumps(event, default=str)}")
        return error_response(f"Failed to trigger EOL scan: {str(e)}")


def scan_github_repos(github_target, github_token=None):
    """Scan GitHub for repositories using the same logic as repo_scanner"""
    try:
        logger.info(f"Discovering repos for target: {github_target}")
        logger.info(f"Token provided: {'Yes' if github_token else 'No'}")

        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
            logger.info("Using GitHub token for authentication")

        # Determine if it's a user or org
        if "/" in github_target:
            # Single repo
            url = f"https://api.github.com/repos/{github_target}"
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return [response.json()]
        else:
            # Try multiple endpoints like repo_scanner does
            repo_type = "all" if github_token else "public"

            # If token provided, try authenticated user endpoint first (gets private repos)
            if github_token:
                auth_user_url = (
                    f"https://api.github.com/user/repos?per_page=100&type={repo_type}"
                )
                logger.info(f"Trying authenticated user endpoint: {auth_user_url}")
                result = _fetch_repos_eol(auth_user_url, headers)
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
            user_url = f"https://api.github.com/users/{github_target}/repos?per_page=100&type={repo_type}"
            logger.info(f"Trying user endpoint: {user_url}")
            result = _fetch_repos_eol(user_url, headers)
            if result:
                logger.info(
                    f"Successfully found {len(result)} repos from user endpoint"
                )
                return result

            # If user endpoint fails, try org endpoint
            org_url = f"https://api.github.com/orgs/{github_target}/repos?per_page=100&type={repo_type}"
            logger.info(f"Trying org endpoint: {org_url}")
            result = _fetch_repos_eol(org_url, headers)
            if result:
                logger.info(f"Successfully found {len(result)} repos from org endpoint")
                return result

        logger.warning("No repositories found for target")
        return []

    except Exception as e:
        logger.error(f"Error scanning GitHub repos: {str(e)}")
        return []


def _fetch_repos_eol(url, headers):
    """Fetch repositories from a single endpoint for EOL scanner"""
    try:
        logger.info(f"Fetching repos from: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        logger.info(f"Response status: {response.status_code}")

        if response.status_code == 200:
            repos = response.json()
            logger.info(f"Found {len(repos)} repositories")
            # Debug: Log first few repo names and visibility
            for idx, repo in enumerate(repos[:5]):
                logger.info(
                    f"Repo {idx+1}: {repo.get('name')} (private: {repo.get('private', False)})"
                )
            return repos
        elif response.status_code == 403:
            if "rate limit" in response.text.lower():
                logger.error(
                    "GitHub API rate limit exceeded. Please add a GitHub token for higher limits."
                )
                raise Exception(
                    "GitHub API rate limit exceeded. Please provide a GitHub token."
                )
            else:
                logger.warning(f"GitHub API access denied: {response.text[:200]}")
        elif response.status_code == 404:
            logger.info(f"GitHub user/org not found at {url}")
        else:
            logger.warning(
                f"API request failed with status {response.status_code}: {response.text[:500]}"
            )
    except Exception as e:
        if "rate limit" in str(e):
            raise  # Re-raise rate limit errors
        logger.error(f"Error fetching repos from {url}: {str(e)}")
    return None


def scan_repo_dependencies(repo, github_token=None):
    """Scan repository for dependency files and check EOL status"""
    try:
        findings = []
        headers = {"Accept": "application/vnd.github.v3+json"}
        if github_token:
            headers["Authorization"] = f"token {github_token}"

        logger.info(f"Scanning repo {repo.get('name')} for dependencies")

        # Recursively scan for dependency files
        findings = scan_directory_recursive(repo, "", headers)

        logger.info(f"Repo {repo.get('name')}: cataloged {len(findings)} technologies")

        # Add GitHub URLs to findings
        repo_url = repo.get("html_url", "")
        for finding in findings:
            file_path = finding.get("file_path")
            if file_path and repo_url:
                github_url = f"{repo_url}/blob/main/{file_path}"
                if finding.get("line_number"):
                    github_url += f"#L{finding['line_number']}"
                finding["github_url"] = github_url
                finding[
                    "source"
                ] = github_url  # Also set as 'source' for frontend compatibility
                logger.info(
                    f"  - {finding.get('tech_type')}:{finding.get('technology')}:{finding.get('version')} (source: {github_url})"
                )
            else:
                finding["source"] = repo_url or "N/A"  # Fallback to repo URL
                logger.info(
                    f"  - {finding.get('tech_type')}:{finding.get('technology')}:{finding.get('version')} (risk: {finding.get('risk_level')})"
                )

        return findings

    except Exception as e:
        logger.error(f"Error scanning repo dependencies: {str(e)}")
        return []


def scan_directory_recursive(repo, path, headers, max_depth=3, current_depth=0):
    """Recursively scan directory for dependency files"""
    findings = []

    if current_depth > max_depth:
        return findings

    try:
        # Get directory contents
        dir_url = (
            f"{repo['url']}/contents/{path}" if path else f"{repo['url']}/contents"
        )
        response = requests.get(dir_url, headers=headers, timeout=30)

        if response.status_code != 200:
            return findings

        contents = response.json()
        if not isinstance(contents, list):
            return findings

        # Define dependency files to look for
        dependency_files = {
            "requirements.txt",
            "pyproject.toml",
            "Pipfile",
            "setup.py",  # Python
            "package.json",
            "yarn.lock",
            "package-lock.json",  # Node.js
            "Dockerfile",
            "docker-compose.yml",  # Docker
            "pom.xml",
            "build.gradle",
            "gradle.properties",  # Java
            "Gemfile",
            "Gemfile.lock",  # Ruby
            "go.mod",
            "go.sum",  # Go
            "Cargo.toml",  # Rust
            "composer.json",  # PHP
            ".python-version",
            ".node-version",
            ".ruby-version",  # Runtime versions
            "runtime.txt",
            "Procfile",  # Heroku/deployment
        }

        # Skip certain directories
        skip_dirs = {
            ".git",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "venv",
            "env",
            ".venv",
            "build",
            "dist",
            ".tox",
            "target",
        }

        for item in contents:
            item_name = item.get("name", "")
            item_type = item.get("type", "")

            if item_type == "file" and item_name in dependency_files:
                # Found a dependency file
                logger.info(
                    f"Found dependency file: {path}/{item_name}"
                    if path
                    else f"Found dependency file: {item_name}"
                )
                try:
                    content = requests.get(item["download_url"], timeout=30).text
                    item_path = f"{path}/{item_name}" if path else item_name
                    file_findings = parse_dependency_file(
                        item_name, content, repo, item_path
                    )
                    logger.info(
                        f"Cataloged {len(file_findings)} technologies in {item_name}"
                    )
                    findings.extend(file_findings)
                except Exception as e:
                    logger.error(f"Error parsing {item_name}: {str(e)}")

            elif item_type == "dir" and item_name not in skip_dirs:
                # Recursively scan subdirectory
                subdir_path = f"{path}/{item_name}" if path else item_name
                subdir_findings = scan_directory_recursive(
                    repo, subdir_path, headers, max_depth, current_depth + 1
                )
                findings.extend(subdir_findings)

        return findings

    except Exception as e:
        logger.error(f"Error scanning directory {path}: {str(e)}")
        return findings


def parse_dependency_file(filename, content, repo=None, file_path=""):
    """Parse dependency file and catalog technologies with EOL check"""
    findings = []

    try:
        # Python files
        if filename in ["requirements.txt", "Pipfile"]:
            for line_num, line in enumerate(content.split("\n"), 1):
                line = line.strip()
                if line and not line.startswith("#"):
                    match = re.match(r"([a-zA-Z0-9_-]+)([>=<~!]+)?([\d.]+)?", line)
                    if match:
                        package, operator, version = match.groups()
                        catalog_entry = catalog_and_check_eol(
                            "python-package",
                            package,
                            version,
                            repo.get("name", "unknown"),
                        )
                        catalog_entry["file_path"] = file_path
                        catalog_entry["line_number"] = line_num
                        findings.append(catalog_entry)

        elif filename == "pyproject.toml":
            # Basic TOML parsing for Python version
            if "python_requires" in content:
                match = re.search(r'python_requires\s*=\s*["\'](.+?)["\']', content)
                if match:
                    version = re.sub(r"[^0-9.]", "", match.group(1))
                    catalog_entry = catalog_and_check_eol(
                        "language", "python", version, repo.get("name", "unknown")
                    )
                    catalog_entry["file_path"] = file_path
                    findings.append(catalog_entry)

        elif filename == ".python-version":
            version = content.strip()
            catalog_entry = catalog_and_check_eol(
                "language", "python", version, repo.get("name", "unknown")
            )
            catalog_entry["file_path"] = file_path
            findings.append(catalog_entry)

        # Node.js files
        elif filename == "package.json":
            try:
                data = json.loads(content)
                # Check Node.js version
                if "engines" in data and "node" in data["engines"]:
                    node_version = re.sub(r"[^0-9.]", "", data["engines"]["node"])
                    catalog_entry = catalog_and_check_eol(
                        "language", "nodejs", node_version, repo.get("name", "unknown")
                    )
                    catalog_entry["file_path"] = file_path
                    catalog_entry["line_number"] = find_json_line(content, "engines")
                    findings.append(catalog_entry)

                # Check dependencies
                dependencies = {
                    **data.get("dependencies", {}),
                    **data.get("devDependencies", {}),
                }
                for package, version in dependencies.items():
                    clean_version = re.sub(r"[^0-9.]", "", version)
                    catalog_entry = catalog_and_check_eol(
                        "npm-package",
                        package,
                        clean_version,
                        repo.get("name", "unknown"),
                    )
                    catalog_entry["file_path"] = file_path
                    catalog_entry["line_number"] = find_json_line(content, package)
                    findings.append(catalog_entry)
            except json.JSONDecodeError:
                pass

        elif filename == ".node-version":
            version = content.strip()
            catalog_entry = catalog_and_check_eol(
                "language", "nodejs", version, repo.get("name", "unknown")
            )
            catalog_entry["file_path"] = file_path
            findings.append(catalog_entry)

        # Docker files
        elif filename in ["Dockerfile", "docker-compose.yml"]:
            for line in content.split("\n"):
                if line.strip().upper().startswith("FROM"):
                    image = line.split()[1] if len(line.split()) > 1 else ""
                    if ":" in image:
                        base_image, tag = image.split(":", 1)
                        # Map common images to languages
                        if "python" in base_image:
                            catalog_entry = catalog_and_check_eol(
                                "language", "python", tag, repo.get("name", "unknown")
                            )
                        elif "node" in base_image:
                            catalog_entry = catalog_and_check_eol(
                                "language", "nodejs", tag, repo.get("name", "unknown")
                            )
                        elif "ubuntu" in base_image:
                            catalog_entry = catalog_and_check_eol(
                                "language", "ubuntu", tag, repo.get("name", "unknown")
                            )
                        elif "alpine" in base_image:
                            catalog_entry = catalog_and_check_eol(
                                "language", "alpine", tag, repo.get("name", "unknown")
                            )
                        else:
                            catalog_entry = catalog_and_check_eol(
                                "docker-image",
                                base_image,
                                tag,
                                repo.get("name", "unknown"),
                            )

                        catalog_entry["file_path"] = file_path
                        findings.append(catalog_entry)

        # Ruby files
        elif filename == "Gemfile":
            # Check Ruby version
            ruby_match = re.search(r'ruby\s+["\'](.+?)["\']', content)
            if ruby_match:
                version = ruby_match.group(1)
                catalog_entry = catalog_and_check_eol(
                    "language", "ruby", version, repo.get("name", "unknown")
                )
                catalog_entry["file_path"] = file_path
                findings.append(catalog_entry)

        elif filename == ".ruby-version":
            version = content.strip()
            catalog_entry = catalog_and_check_eol(
                "language", "ruby", version, repo.get("name", "unknown")
            )
            catalog_entry["file_path"] = file_path
            findings.append(catalog_entry)

        # Java files
        elif filename == "pom.xml":
            # Check Java version in Maven
            java_match = re.search(
                r"<maven\.compiler\.source>([^<]*)</maven\.compiler\.source>", content
            )
            if java_match:
                version = java_match.group(1)
                catalog_entry = catalog_and_check_eol(
                    "language", "java", version, repo.get("name", "unknown")
                )
                catalog_entry["file_path"] = file_path
                findings.append(catalog_entry)

        # Go files
        elif filename == "go.mod":
            go_match = re.search(r"go\s+([0-9.]+)", content)
            if go_match:
                version = go_match.group(1)
                catalog_entry = catalog_and_check_eol(
                    "language", "go", version, repo.get("name", "unknown")
                )
                catalog_entry["file_path"] = file_path
                findings.append(catalog_entry)

        # Rust files
        elif filename == "Cargo.toml":
            # Check Rust edition
            edition_match = re.search(r'edition\s*=\s*["\'](.+?)["\']', content)
            if edition_match:
                edition = edition_match.group(1)
                catalog_entry = catalog_and_check_eol(
                    "language", "rust", edition, repo.get("name", "unknown")
                )
                catalog_entry["file_path"] = file_path
                findings.append(catalog_entry)

    except Exception as e:
        logger.error(f"Error parsing {filename}: {str(e)}")

    return findings


def find_json_line(content, key):
    """Find line number of a key in JSON content"""
    try:
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            if f'"{key}"' in line:
                return i
    except Exception:
        pass
    return 1


def catalog_and_check_eol(tech_type, name, version, repo_name):
    """Catalog technology and check EOL status"""
    try:
        # Always catalog the technology
        current_time = datetime.now(timezone.utc).isoformat()
        catalog_entry = {
            "technology": name,
            "version": version or "unknown",
            "tech_type": tech_type,
            "repo_name": repo_name,
            "last_seen": current_time,
            "eol_date": None,
            "risk_level": "unknown",
            "file_path": None,
            "line_number": None,
        }

        # Check for EOL status
        eol_id = f"{tech_type}:{name}"
        response = eol_database_table.get_item(Key={"eol_id": eol_id})

        if "Item" in response:
            eol_data = response["Item"]
            eol_date = eol_data.get("eol_date")
            if eol_date:
                risk_level = calculate_risk_level(eol_date)
                catalog_entry.update({"eol_date": eol_date, "risk_level": risk_level})
                logger.info(
                    f"Found cached EOL data for {name}: {eol_date} (risk: {risk_level})"
                )
        else:
            # Try to fetch EOL data from API
            api_name = map_to_eol_api_name(name)
            logger.info(f"Mapping {name} to API name: {api_name}")
            if api_name:
                eol_info = fetch_from_eol_api(api_name, version)
                if eol_info:
                    store_eol_data(eol_id, tech_type, name, eol_info)
                    catalog_entry.update(
                        {
                            "eol_date": eol_info.get("eol_date"),
                            "risk_level": eol_info.get("risk_level", "unknown"),
                        }
                    )
                    logger.info(
                        f"Fetched new EOL data for {name}: {eol_info.get('eol_date')} (risk: {eol_info.get('risk_level')})"
                    )
                else:
                    logger.info(f"No EOL data found for {name} (mapped to {api_name})")
            else:
                logger.info(f"No API mapping found for {name}")

        # Return catalog entry (always return for inventory)
        return catalog_entry

    except Exception as e:
        logger.error(f"Error cataloging {name}: {str(e)}")
        return {
            "technology": name,
            "version": version or "unknown",
            "tech_type": tech_type,
            "repo_name": repo_name,
            "risk_level": "error",
            "error": str(e)[:100],
        }


def check_eol_status(tech_type, name, version):
    """Legacy function - now just calls catalog_and_check_eol"""
    catalog_entry = catalog_and_check_eol(tech_type, name, version, "unknown")
    # Only return if there's an actual EOL risk
    if catalog_entry.get("risk_level") in ["critical", "high", "medium"]:
        return catalog_entry
    return None


def calculate_risk_level(eol_date):
    """Calculate risk level based on EOL date"""
    try:
        if not eol_date or eol_date is False:
            return "unknown"

        # Handle different date formats
        if isinstance(eol_date, str):
            if eol_date.endswith("Z"):
                eol_datetime = datetime.fromisoformat(eol_date.replace("Z", "+00:00"))
            elif "T" in eol_date:
                eol_datetime = datetime.fromisoformat(eol_date)
            elif len(eol_date) == 10 and "-" in eol_date:  # YYYY-MM-DD
                eol_datetime = datetime.strptime(eol_date, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            else:
                logger.warning(f"Unknown date format: {eol_date}")
                return "unknown"
        else:
            return "unknown"

        now = datetime.now(timezone.utc)
        days_until_eol = (eol_datetime - now).days

        if days_until_eol < 0:
            return "critical"  # Already EOL
        elif days_until_eol < 90:
            return "high"  # EOL within 3 months
        elif days_until_eol < 365:
            return "medium"  # EOL within 1 year
        else:
            return "low"  # EOL more than 1 year away

    except Exception as e:
        logger.warning(f"Error calculating risk level for {eol_date}: {str(e)}")
        return "unknown"


def map_to_eol_api_name(name):
    """Map technology name to EOL API name with expanded coverage"""
    # Handle @aws-sdk/ scoped packages - use AWS SDK API first
    if name.startswith("@aws-sdk/"):
        return "aws-sdk"  # Use AWS SDK support matrix

    mapping = {
        # Languages
        "python": "python",
        "node": "node",
        "nodejs": "node",
        "ruby": "ruby",
        "java": "java",
        "go": "go",
        "rust": "rust",
        "php": "php",
        "dotnet": "dotnet",
        "csharp": "dotnet",
        "c#": "dotnet",
        # Operating Systems
        "ubuntu": "ubuntu",
        "debian": "debian",
        "alpine": "alpine",
        "centos": "centos",
        "rhel": "rhel",
        "amazonlinux": "amazon-linux",
        "windows": "windows",
        # Databases
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "mysql": "mysql",
        "redis": "redis",
        "mongodb": "mongodb",
        "elasticsearch": "elasticsearch",
        "mariadb": "mariadb",
        "sqlite": "sqlite",
        # Frameworks
        "django": "django",
        "rails": "rails",
        "laravel": "laravel",
        "spring": "spring-framework",
        "react": "react",
        "angular": "angular",
        "vue": "vue",
        "express": "express",
        "nextjs": "node",
        "nuxt": "node",
        # AWS SDKs (use official support matrix)
        "boto3": "python",  # boto3 follows Python lifecycle, not AWS SDK succession
        "botocore": "python",  # botocore should use Python EOL, not AWS SDK matrix
        "aws-sdk": "aws-sdk",
        "aws-sdk-js": "aws-sdk",
        "aws-java-sdk": "aws-sdk",
        "aws-sdk-go": "aws-sdk",
        "aws-sdk-php": "aws-sdk",
        "aws-sdk-ruby": "aws-sdk",
        "aws-cdk": "aws-sdk",
        "aws-cdk-lib": "aws-sdk",
        # Common Python packages
        "flask": "flask",
        "fastapi": "python",
        "requests": "python",
        "numpy": "python",
        "pandas": "python",
        "sqlalchemy": "python",
        "celery": "python",
        "gunicorn": "python",
        # Common Node packages
        "lodash": "node",
        "axios": "node",
        "moment": "node",
        "webpack": "node",
        "babel": "node",
        "eslint": "node",
        # Infrastructure
        "docker": "docker-engine",
        "kubernetes": "kubernetes",
        "terraform": "terraform",
        "ansible": "ansible",
        "jenkins": "jenkins",
        "nginx": "nginx",
        "apache": "apache",
        "tomcat": "tomcat",
    }
    return mapping.get(name.lower())


def fetch_from_eol_api(api_name, version):
    """Fetch EOL data from multiple sources"""
    # Try AWS SDK first for AWS packages, then other sources
    sources = [
        ("aws-sdk", fetch_from_aws_sdk_api),
        ("endoflife.date", fetch_from_endoflife_api),
        ("github-advisories", fetch_from_github_advisories),
    ]

    logger.info(f"Fetching EOL data for {api_name} version {version}")

    for source_name, fetch_func in sources:
        try:
            result = fetch_func(api_name, version)
            if result:
                logger.info(
                    f"Found EOL data from {source_name} for {api_name}: {result}"
                )
                return result
            else:
                logger.info(f"No data from {source_name} for {api_name}")
        except Exception as e:
            logger.warning(f"Error fetching from {source_name}: {str(e)}")

    logger.info(f"No EOL data found for {api_name} from any source")
    return None


def fetch_from_endoflife_api(api_name, version):
    """Fetch EOL data from endoflife.date API"""
    try:
        url = f"https://endoflife.date/api/{api_name}.json"
        logger.info(f"Fetching EOL data from: {url}")
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            logger.info(f"Got {len(data)} versions for {api_name}")

            # Find matching version or use latest
            best_match = None

            for item in data:
                cycle = str(item.get("cycle", ""))
                eol_date = item.get("eol")

                # Skip if no EOL date or EOL is False (never expires)
                if not eol_date or eol_date is False:
                    continue

                # Exact version match
                if version and cycle == str(version):
                    best_match = item
                    break
                # Partial version match (e.g., "3.9" matches "3.9.1")
                elif version and cycle.startswith(str(version)):
                    best_match = item
                    break
                # Major version match (e.g., "3" matches "3.9")
                elif version and cycle.split(".")[0] == str(version).split(".")[0]:
                    if not best_match:
                        best_match = item

            # If no version match, use the latest (first item)
            if not best_match and data:
                best_match = data[0]
                if not best_match.get("eol") or best_match.get("eol") is False:
                    best_match = None

            if best_match:
                eol_date = best_match.get("eol")
                if eol_date and eol_date is not False:
                    # Convert date to ISO format if needed
                    if isinstance(eol_date, str):
                        try:
                            # Handle different date formats
                            if len(eol_date) == 10 and "-" in eol_date:  # YYYY-MM-DD
                                parsed_date = datetime.strptime(eol_date, "%Y-%m-%d")
                                eol_date = parsed_date.isoformat() + "Z"
                            elif not eol_date.endswith("Z") and "T" not in eol_date:
                                eol_date = eol_date + "T00:00:00Z"
                        except Exception as e:
                            logger.warning(
                                f"Date parsing failed for {eol_date}: {str(e)}"
                            )
                            return None

                    risk_level = calculate_risk_level(eol_date)
                    logger.info(
                        f"Found EOL data for {api_name} v{best_match.get('cycle')}: {eol_date} (risk: {risk_level})"
                    )

                    return {
                        "eol_date": eol_date,
                        "risk_level": risk_level,
                        "cycle": str(best_match.get("cycle", version)),
                    }
        else:
            logger.warning(f"EOL API returned {response.status_code} for {api_name}")

        return None

    except Exception as e:
        logger.error(f"Error fetching from EOL API for {api_name}: {str(e)}")
        return None


def fetch_from_aws_sdk_api(api_name, version):
    """Fetch EOL data for AWS SDKs from official support matrix"""
    try:
        # Check if this is an AWS SDK package
        if not is_aws_sdk_package(api_name):
            return None

        logger.info(f"Processing AWS SDK package: {api_name}")

        # Try to fetch from AWS SDK support matrix
        sdk_data = fetch_aws_sdk_support_matrix()
        if sdk_data:
            return get_aws_sdk_eol_from_matrix(api_name, version, sdk_data)

        # Fallback to language-based EOL for AWS SDKs
        aws_mappings = {
            "boto3": "python",
            "botocore": "python",
            "aws-sdk": "node",
            "aws-java-sdk": "java",
            "aws-sdk-go": "go",
            "aws-sdk-php": "php",
            "aws-sdk-ruby": "ruby",
            "aws-cdk": "node",
        }

        if api_name in aws_mappings:
            return fetch_from_endoflife_api(aws_mappings[api_name], version)

        return None

    except Exception as e:
        logger.error(f"Error fetching AWS SDK EOL data: {str(e)}")
        return None


def is_aws_sdk_package(name):
    """Check if package is an AWS SDK"""
    aws_patterns = [
        "@aws-sdk/",
        "aws-sdk",
        "boto3",
        "botocore",
        "boto2",
        "aws-java-sdk",
        "aws-sdk-go",
        "aws-sdk-php",
        "aws-sdk-ruby",
        "aws-cdk",
    ]
    return any(pattern in name.lower() for pattern in aws_patterns)


def fetch_aws_sdk_support_matrix():
    """Fetch AWS SDK support matrix from official docs"""
    try:
        url = "https://docs.aws.amazon.com/sdkref/latest/guide/version-support-matrix.html"
        response = requests.get(url, timeout=15)

        if response.status_code == 200:
            return parse_aws_support_matrix(response.text)

        logger.warning(f"AWS support matrix returned {response.status_code}")
        return None

    except Exception as e:
        logger.error(f"Error fetching AWS support matrix: {str(e)}")
        return None


def extract_boto3_ga_date(html):
    """Extract boto3 GA date from AWS documentation"""
    import re

    patterns = [
        r"Python.*?(?:GA|General Availability).*?(\d{1,2}/\d{1,2}/\d{4})",
        r"boto3.*?(?:GA|General Availability).*?(\d{1,2}/\d{1,2}/\d{4})",
        r"Python.*?(\d{1,2}/\d{1,2}/\d{4}).*?(?:GA|General Availability)",
    ]

    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE)
        if match:
            try:
                parsed = datetime.strptime(match.group(1), "%m/%d/%Y")
                return parsed.isoformat() + "Z"
            except Exception:
                continue
    return "2015-06-23T00:00:00Z"


def parse_aws_support_matrix(html_content):
    """Parse AWS SDK support matrix HTML"""
    try:
        boto3_ga_date = extract_boto3_ga_date(html_content)

        sdk_data = {
            "aws-sdk-v2": {
                "status": "End-of-Support",
                "eol_date": "2020-12-15T00:00:00Z",
                "risk_level": "critical",
                "successor_version": "3.x",
            },
            "aws-sdk-v3": {
                "status": "General Availability",
                "ga_date": "2020-12-15T00:00:00Z",
                "eol_date": None,
                "risk_level": "low",
            },
            "boto2": {
                "status": "End-of-Support",
                "eol_date": boto3_ga_date,
                "risk_level": "critical",
                "successor_version": "boto3",
            },
            "boto3": {
                "status": "General Availability",
                "eol_date": None,
                "risk_level": "low",
                "successor_check": "boto4",
            },
            "botocore": {
                "status": "General Availability",
                "eol_date": None,
                "risk_level": "low",
                "successor_check": None,
            },
        }

        logger.info(f"Parsed AWS SDK data: {sdk_data}")
        return sdk_data

    except Exception as e:
        logger.error(f"Error parsing AWS support matrix: {str(e)}")
        return None


def map_sdk_to_key(api_name, version):
    """Map SDK name and version to matrix key"""
    if api_name.startswith("@aws-sdk/"):
        return "aws-sdk-v3"
    elif api_name == "aws-sdk":
        if version and version.startswith("2."):
            return "aws-sdk-v2"
        elif version and version.startswith("3."):
            return "aws-sdk-v3"
        else:
            return "aws-sdk-v2"  # Default to v2
    elif api_name in ["boto3", "botocore", "boto2"]:
        return api_name
    return None


def get_aws_sdk_eol_from_matrix(api_name, version, sdk_data):
    """Get EOL data for specific AWS SDK from matrix data"""
    try:
        logger.info(f"Processing AWS SDK: {api_name} version {version}")

        sdk_key = map_sdk_to_key(api_name, version)
        if not sdk_key or sdk_key not in sdk_data:
            return None

        logger.info(f"Mapped {api_name} to SDK key: {sdk_key}")
        data = sdk_data[sdk_key]

        if data.get("status") == "End-of-Support":
            return {
                "eol_date": data["eol_date"],
                "risk_level": data["risk_level"],
                "cycle": version or "2.x",
                "status": "End-of-Support",
                "successor_version": data.get("successor_version"),
            }

        if data.get("status") == "General Availability":
            successor_check = data.get("successor_check")
            if successor_check and successor_check in sdk_data:
                successor_data = sdk_data[successor_check]
                if successor_data.get("ga_date"):
                    return {
                        "eol_date": successor_data["ga_date"],
                        "risk_level": "critical",
                        "cycle": version or "current",
                        "status": "End-of-Support",
                        "successor_version": successor_check,
                    }

            return {
                "eol_date": None,
                "risk_level": "low",
                "cycle": version or "current",
                "status": "Current Supported Release",
            }

        return None

    except Exception as e:
        logger.error(f"Error getting SDK EOL from matrix: {str(e)}")
        return None


def fetch_from_github_advisories(api_name, version):
    """Fetch EOL data from GitHub Security Advisories"""
    try:
        # Common packages with known EOL patterns
        github_mappings = {
            "express": {"base_language": "nodejs"},
            "flask": {"base_language": "python"},
            "django": {"base_language": "python"},
            "rails": {"base_language": "ruby"},
            "spring": {"base_language": "java"},
            "react": {"base_language": "nodejs"},
            "angular": {"base_language": "nodejs"},
            "vue": {"base_language": "nodejs"},
        }

        if api_name in github_mappings:
            base_lang = github_mappings[api_name]["base_language"]
            return fetch_from_endoflife_api(base_lang, version)

        return None

    except Exception as e:
        logger.error(f"Error fetching GitHub advisories: {str(e)}")
        return None


def store_eol_data(eol_id, tech_type, name, eol_info):
    """Store EOL data in database"""
    try:
        eol_database_table.put_item(
            Item={
                "eol_id": eol_id,
                "technology_type": tech_type,
                "name": name,
                "eol_date": eol_info.get("eol_date"),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "ttl": int((datetime.now() + timedelta(days=30)).timestamp()),
            }
        )
    except Exception as e:
        logger.error(f"Error storing EOL data: {str(e)}")


def get_eol_scans(event):
    """Get EOL scan history for user"""
    try:
        user_id = event["user_info"]["user_id"]

        response = eol_scans_table.query(
            IndexName="user-id-index",
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
            ScanIndexForward=False,
            Limit=20,
        )

        scans = response.get("Items", [])

        return success_response({"scans": scans, "total": len(scans)})

    except Exception as e:
        logger.error(f"Error getting EOL scans: {str(e)}")
        return error_response("Failed to get EOL scans")


def cleanup_user_scans(event):
    """Delete all EOL scan data for the authenticated user"""
    try:
        user_id = event["user_info"]["user_id"]

        # Get all scans for the user
        response = eol_scans_table.query(
            IndexName="user-id-index",
            KeyConditionExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        scans = response.get("Items", [])
        deleted_count = 0

        # Delete each scan
        for scan in scans:
            scan_id = scan.get("scan_id")
            if scan_id:
                eol_scans_table.delete_item(Key={"scan_id": scan_id})
                deleted_count += 1

        logger.info(f"Deleted {deleted_count} EOL scans for user {user_id}")

        return success_response(
            {
                "message": f"Successfully deleted {deleted_count} EOL scans",
                "deleted_count": deleted_count,
            }
        )

    except Exception as e:
        logger.error(f"Error cleaning up user scans: {str(e)}")
        return error_response("Failed to cleanup scan data")


def get_eol_database(event):
    """Get EOL database entries"""
    try:
        response = eol_database_table.scan(Limit=100)
        items = response.get("Items", [])

        return success_response({"eol_data": items, "total": len(items)})

    except Exception as e:
        logger.error(f"Error getting EOL database: {str(e)}")
        return error_response("Failed to get EOL database")


def success_response(data):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps(data, default=str),
    }


def error_response(message, status_code=400):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": json.dumps({"error": message}),
    }


def cors_response():
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        },
        "body": "",
    }
