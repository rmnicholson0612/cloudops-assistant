import json
import logging
import os
import re
from datetime import datetime, timezone

import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

pr_reviews_table_name = os.environ.get(
    "PR_REVIEWS_TABLE", "cloudops-assistant-pr-reviews"
)
pr_reviews_table = dynamodb.Table(pr_reviews_table_name)


def lambda_handler(event, context):
    """Analyze PR changes and post AI review"""
    review_id = event.get("review_id")
    try:
        pr_data = event.get("pr_data", {})
        repo_token = event.get("repo_token")

        # Sanitize review_id for logging to prevent log injection
        safe_review_id = (
            str(review_id).replace("\n", "").replace("\r", "")[:50]
            if review_id
            else "unknown"
        )
        logger.info(f"Analyzing PR review: {safe_review_id}")

        # Get PR diff from GitHub
        diff_content = get_pr_diff(pr_data, repo_token)

        # Generate AI review
        ai_review = generate_ai_review(diff_content, pr_data)

        # Post review comment to GitHub
        comment_posted = post_github_comment(pr_data, ai_review, repo_token)

        # Update review record
        pr_reviews_table.update_item(
            Key={"review_id": review_id},
            UpdateExpression="SET #status = :status, ai_review = :review, analyzed_at = :timestamp, comment_posted = :posted",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": "completed",
                ":review": ai_review,
                ":timestamp": datetime.now(timezone.utc).isoformat(),
                ":posted": comment_posted,
            },
        )

        logger.info(f"PR review completed: {safe_review_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({"review_id": review_id, "status": "completed"}),
        }

    except Exception as e:
        logger.error(f"PR analysis error: {str(e)}")
        # Update status to failed if review_id exists
        if review_id:
            pr_reviews_table.update_item(
                Key={"review_id": review_id},
                UpdateExpression="SET #status = :status, error_message = :error",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "failed", ":error": str(e)},
            )
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_pr_diff(pr_data, repo_token=None):
    """Get PR files and changes from GitHub API"""
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if repo_token:
            headers["Authorization"] = f"token {repo_token}"

        # Validate and sanitize URL components to prevent SSRF
        repo_full_name, pr_number = _validate_pr_params(pr_data)
        if not repo_full_name:
            return f"PR #{pr_number}: Invalid repository format"
        if not pr_number:
            return "PR: Invalid PR number format"

        # Get PR files to see what changed
        files_url = (
            f"https://api.github.com/repos/{repo_full_name}/pulls/{pr_number}/files"
        )
        files_response = requests.get(files_url, headers=headers, timeout=30)

        if files_response.status_code == 200:
            files = files_response.json()

            # Build summary of changes
            changes_summary = (
                f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}\n\nChanged files:\n"
            )

            for file in files[:10]:  # Limit to first 10 files
                filename = file.get("filename", "")
                status = file.get("status", "")
                additions = file.get("additions", 0)
                deletions = file.get("deletions", 0)

                changes_summary += (
                    f"- {filename} ({status}): +{additions}/-{deletions}\n"
                )

                # Include patch for small files
                if file.get("patch") and len(file["patch"]) < 2000:
                    changes_summary += (
                        f"\nChanges in {filename}:\n{file['patch'][:1000]}\n\n"
                    )

            return changes_summary[:8000]  # Limit total size

        logger.warning(f"Failed to get PR files: {files_response.status_code}")
        return f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}\nUnable to fetch file changes."

    except Exception as e:
        logger.error(f"Error getting PR files: {str(e)}")
        return f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}\nError fetching changes: {str(e)}"


def generate_ai_review(diff_content, pr_data):
    """Generate AI review using Bedrock"""
    try:
        prompt = f"""You are a senior code reviewer. Review this PR and provide a conversational analysis like ChatGPT would.

PR: {pr_data['pr_title']}
Repository: {pr_data['repo_name']}

Changes:
{diff_content}

Provide a thorough review covering:
1. Overall risk level (LOW/MEDIUM/HIGH)
2. Security concerns if any
3. Code quality issues
4. Specific actionable recommendations

Respond in JSON format with these exact keys:
- risk_level: "LOW", "MEDIUM", or "HIGH"
- security_issues: array of strings (each a complete sentence)
- violations: array of strings (each a complete sentence)
- recommendations: array of strings (each a complete actionable recommendation)

Keep each array item as a single clear sentence. Do not include nested objects or code blocks."""

        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1000, "temperature": 0.3},
        }

        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0", body=json.dumps(body)
        )

        result = json.loads(response["body"].read().decode("utf-8"))

        # Extract AI text with simplified error handling
        ai_text = _extract_ai_text(result)
        return _parse_ai_response(ai_text)

    except Exception as e:
        logger.error(f"AI review generation failed: {str(e)}")
        return {
            "risk_level": "LOW",
            "security_issues": [],
            "violations": [],
            "recommendations": ["AI review unavailable - manual review recommended"],
        }


def post_github_comment(pr_data, ai_review, repo_token=None):
    """Post AI review as GitHub comment"""
    try:
        if not repo_token:
            logger.info("No GitHub token, skipping comment posting")
            return False

        risk_emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚨"}
        emoji = risk_emoji.get(ai_review.get("risk_level", "MEDIUM"), "⚠️")

        comment = f"""## {emoji} CloudOps AI Review

**Risk Level:** {ai_review.get('risk_level', 'MEDIUM')}

**Security Issues:**
{format_list(ai_review.get('security_issues', []))}

**Best Practice Violations:**
{format_list(ai_review.get('violations', []))}

**Recommendations:**
{format_list(ai_review.get('recommendations', []))}

---
*Automated review by CloudOps Assistant*"""

        headers = {
            "Authorization": f"token {repo_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        # Validate and sanitize URL components to prevent SSRF
        repo_full_name, pr_number = _validate_pr_params(pr_data)
        if not repo_full_name or not pr_number:
            return False

        url = (
            f"https://api.github.com/repos/{repo_full_name}/issues/{pr_number}/comments"
        )
        response = requests.post(
            url, headers=headers, json={"body": comment}, timeout=30
        )

        return response.status_code == 201

    except Exception as e:
        logger.error(f"Failed to post GitHub comment: {str(e)}")
        return False


def _validate_pr_params(pr_data):
    """Validate and sanitize PR parameters"""
    repo_full_name = str(pr_data.get("repo_full_name", "")).strip()
    pr_number = str(pr_data.get("pr_number", "")).strip()

    # Validate repo_full_name format (owner/repo)
    if (
        not re.match(r"^[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+$", repo_full_name)
        or len(repo_full_name) > 100
    ):
        logger.error(f"Invalid repo_full_name format: {repo_full_name}")
        return None, pr_number

    # Validate pr_number is numeric
    if not pr_number.isdigit() or int(pr_number) <= 0:
        logger.error(f"Invalid pr_number: {pr_number}")
        return repo_full_name, None

    return repo_full_name, pr_number


def _extract_ai_text(result):
    """Extract AI text from Bedrock response"""
    try:
        return result["output"]["message"]["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as e:
        logger.error(f"Invalid Bedrock response structure: {str(e)}")
        raise ValueError("Invalid AI response format")


def _parse_ai_response(ai_text):
    """Parse AI response text into structured format"""
    try:
        return json.loads(ai_text)
    except json.JSONDecodeError:
        return {
            "risk_level": "MEDIUM",
            "security_issues": [],
            "violations": [],
            "recommendations": [ai_text[:500]],
        }


def format_list(items):
    """Format list items for markdown"""
    if not items:
        return "- None found"
    return "\n".join(f"- {item}" for item in items[:5])  # Limit to 5 items
