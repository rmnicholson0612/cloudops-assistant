import json
import logging
import os
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
    try:
        review_id = event.get("review_id")
        pr_data = event.get("pr_data", {})
        repo_token = event.get("repo_token")

        logger.info(f"Analyzing PR review: {review_id}")

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

        logger.info(f"PR review completed: {review_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({"review_id": review_id, "status": "completed"}),
        }

    except Exception as e:
        logger.error(f"PR analysis error: {str(e)}")
        # Update status to failed
        if "review_id" in locals():
            pr_reviews_table.update_item(
                Key={"review_id": review_id},
                UpdateExpression="SET #status = :status, error_message = :error",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues={":status": "failed", ":error": str(e)},
            )
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def get_pr_diff(pr_data, repo_token=None):
    """Get PR diff from GitHub API"""
    try:
        headers = {"Accept": "application/vnd.github.v3.diff"}
        if repo_token:
            headers["Authorization"] = f"token {repo_token}"

        url = f"https://api.github.com/repos/{pr_data['repo_full_name']}/pulls/{pr_data['pr_number']}"
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 200:
            return response.text[:8000]  # Limit diff size
        else:
            logger.warning(f"Failed to get PR diff: {response.status_code}")
            return f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}"

    except Exception as e:
        logger.error(f"Error getting PR diff: {str(e)}")
        return f"PR #{pr_data['pr_number']}: {pr_data['pr_title']}"


def generate_ai_review(diff_content, pr_data):
    """Generate AI review using Bedrock"""
    try:
        prompt = f"""Review this infrastructure PR for security and best practices:

PR: {pr_data['pr_title']}
Repository: {pr_data['repo_name']}

Changes:
{diff_content}

Provide:
1. Risk level (LOW/MEDIUM/HIGH)
2. Security issues found
3. Best practice violations
4. Recommendations

Format as JSON with keys: risk_level, security_issues, violations, recommendations"""

        body = {
            "messages": [{"role": "user", "content": [{"text": prompt}]}],
            "inferenceConfig": {"maxTokens": 1000, "temperature": 0.3},
        }

        response = bedrock.invoke_model(
            modelId="amazon.nova-lite-v1:0", body=json.dumps(body)
        )

        result = json.loads(response["body"].read().decode("utf-8"))
        ai_text = result["output"]["message"]["content"][0]["text"]

        try:
            return json.loads(ai_text)
        except json.JSONDecodeError:
            return {
                "risk_level": "MEDIUM",
                "security_issues": [],
                "violations": [],
                "recommendations": [ai_text[:500]],
            }

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

        url = f"https://api.github.com/repos/{pr_data['repo_full_name']}/issues/{pr_data['pr_number']}/comments"
        response = requests.post(
            url, headers=headers, json={"body": comment}, timeout=30
        )

        return response.status_code == 201

    except Exception as e:
        logger.error(f"Failed to post GitHub comment: {str(e)}")
        return False


def format_list(items):
    """Format list items for markdown"""
    if not items:
        return "- None found"
    return "\n".join(f"- {item}" for item in items[:5])  # Limit to 5 items
