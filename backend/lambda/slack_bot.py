import json
import logging
import os
import re
import secrets
import urllib.parse
from datetime import datetime, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
bedrock = boto3.client("bedrock-runtime")
cost_explorer = boto3.client("ce")

# DynamoDB tables
plans_table = dynamodb.Table(
    os.environ.get("TERRAFORM_PLANS_TABLE", "TerraformPlansTable")
)
postmortems_table = dynamodb.Table(
    os.environ.get("POSTMORTEMS_TABLE", "PostmortemsTable")
)
service_docs_table = dynamodb.Table(
    os.environ.get("SERVICE_DOCS_TABLE", "ServiceDocsTable")
)
drift_configs_table = dynamodb.Table(
    os.environ.get("DRIFT_CONFIGS_TABLE", "DriftConfigsTable")
)
cost_cache_table = dynamodb.Table(os.environ.get("COST_CACHE_TABLE", "CostCacheTable"))
mapping_table = dynamodb.Table(
    os.environ.get("SLACK_USER_MAPPING_TABLE", "SlackUserMappingTable")
)

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")


def lambda_handler(event, context):
    """Main Slack bot handler"""
    try:
        logger.info(f"Received event: {json.dumps(event, default=str)[:1000]}")

        # Handle Slack URL verification
        if event.get("body"):
            try:
                body = json.loads(event["body"])
                if body.get("type") == "url_verification":
                    return {"statusCode": 200, "body": body["challenge"]}
            except json.JSONDecodeError:
                # Not JSON, probably form data
                logger.info("Body is not JSON, treating as form data")

        # Parse Slack request
        if event.get("httpMethod") == "POST":
            content_type = event.get("headers", {}).get("Content-Type", "")
            logger.info(f"Content-Type: {content_type}")

            if "application/x-www-form-urlencoded" in content_type:
                # Slash command
                logger.info("Handling as slash command")
                return handle_slash_command(event)
            elif "application/json" in content_type and event.get("body"):
                # Event API
                logger.info("Handling as event API")
                return handle_event(event)
            else:
                # Unknown or empty - return success
                logger.info("Unknown content type or empty body")
                return {"statusCode": 200, "body": "OK"}

        return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def handle_slash_command(event):
    """Handle Slack slash commands"""
    try:
        # Parse form-encoded body from Slack
        if event.get("body"):
            body = urllib.parse.parse_qs(event["body"])
        else:
            body = {}

        command = body.get("command", [""])[0] if body.get("command") else ""
        text = body.get("text", [""])[0].strip() if body.get("text") else ""
        user_id = body.get("user_id", [""])[0] if body.get("user_id") else ""
        channel_id = body.get("channel_id", [""])[0] if body.get("channel_id") else ""

        logger.info(f"Slash command: {command} {text} from user {user_id}")

        if command == "/cloudops":
            return handle_cloudops_command(text, user_id, channel_id)

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {
                    "response_type": "ephemeral",
                    "text": "Unknown command. Try `/cloudops help`",
                }
            ),
        }

    except Exception as e:
        logger.error(f"Slash command error: {str(e)}")
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(
                {"response_type": "ephemeral", "text": f"Error: {str(e)}"}
            ),
        }


def handle_cloudops_command(text, user_id, channel_id):
    """Handle /cloudops commands"""
    parts = text.split() if text else []
    command = parts[0] if parts else "help"

    if command == "help":
        return slack_response(
            {
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "*🤖 CloudOps Assistant Commands*",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "• `/cloudops register` - Link your CloudOps account\n"
                                "• `/cloudops status` - Infrastructure status\n"
                                "• `/cloudops drift [repo]` - Check drift\n"
                                "• `/cloudops costs [service]` - Cost analysis\n"
                                "• `/cloudops incident [title]` - Start incident\n"
                                "• `/cloudops explain [plan-id]` - Explain terraform\n"
                                "• `/cloudops help` - Show this help"
                            ),
                        },
                    },
                ],
            }
        )

    elif command == "register":
        return handle_register_command(user_id)

    elif command == "status":
        return require_auth_or_execute(
            user_id, lambda uid: get_infrastructure_status(uid)
        )

    elif command == "drift":
        repo = parts[1] if len(parts) > 1 else None
        return require_auth_or_execute(user_id, lambda uid: get_drift_status(uid, repo))

    elif command == "costs":
        service = parts[1] if len(parts) > 1 else None
        return require_auth_or_execute(
            user_id, lambda uid: get_cost_status(uid, service)
        )

    elif command == "incident":
        title = " ".join(parts[1:]) if len(parts) > 1 else "New Incident"
        return require_auth_or_execute(user_id, lambda uid: start_incident(uid, title))

    elif command == "explain":
        plan_id = parts[1] if len(parts) > 1 else None
        if not plan_id:
            return slack_response(
                {
                    "response_type": "ephemeral",
                    "text": "Please provide a plan ID: `/cloudops explain plan-123`",
                }
            )
        return require_auth_or_execute(
            user_id, lambda uid: explain_terraform_plan(uid, plan_id)
        )

    else:
        return slack_response(
            {
                "response_type": "ephemeral",
                "text": f"Unknown command: {command}. Try `/cloudops help`",
            }
        )


def handle_event(event):
    """Handle Slack Events API"""
    try:
        if event.get("body"):
            body = json.loads(event["body"])
            event_type = body.get("event", {}).get("type")

            if event_type == "app_mention":
                return handle_mention(body["event"])

        return {"statusCode": 200, "body": ""}

    except Exception as e:
        logger.error(f"Event error: {str(e)}")
        return {"statusCode": 200, "body": ""}


def handle_mention(event_data):
    """Handle @CloudOps mentions"""
    try:
        text = event_data.get("text", "")
        user = event_data.get("user")
        channel = event_data.get("channel")

        # Remove bot mention from text
        clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()

        if not clean_text:
            response = "Hi! I can help with infrastructure questions. Try asking about services, costs, or incidents."
        else:
            response = search_documentation(clean_text, user)

        # Send response to Slack (would need Slack Web API client)
        logger.info(f"Would respond to {user} in {channel}: {response}")

        return {"statusCode": 200, "body": ""}

    except Exception as e:
        logger.error(f"Mention error: {str(e)}")
        return {"statusCode": 200, "body": ""}


def map_slack_user_to_cloudops_user(slack_user_id):
    """Map Slack user ID to CloudOps user ID using DynamoDB"""
    try:
        response = mapping_table.get_item(Key={"slack_user_id": slack_user_id})

        if "Item" in response:
            cognito_user_id = response["Item"]["cognito_user_id"]
            logger.info(
                f"Mapped Slack user {slack_user_id} to Cognito user {cognito_user_id}"
            )
            return cognito_user_id
        else:
            logger.info(f"No mapping found for Slack user {slack_user_id}")
            return None

    except Exception as e:
        logger.error(f"Error mapping user: {str(e)}")
        return None


def require_auth_or_execute(slack_user_id, command_func):
    """Check if user is authenticated, if not prompt to register"""
    cloudops_user_id = map_slack_user_to_cloudops_user(slack_user_id)
    if not cloudops_user_id:
        return slack_response(
            {
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🔐 *Account Not Linked*\n\nYou need to link your CloudOps account first.",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "Run `/cloudops register` to connect your Slack "
                                "account with your existing CloudOps login."
                            ),
                        },
                    },
                ],
            }
        )

    return command_func(cloudops_user_id)


def handle_register_command(slack_user_id):
    """Handle user registration command"""
    try:
        # Check if already registered
        existing_mapping = map_slack_user_to_cloudops_user(slack_user_id)
        if existing_mapping:
            return slack_response(
                {
                    "response_type": "ephemeral",
                    "text": "✅ Your account is already linked! You can use CloudOps commands.",
                }
            )

        # Generate linking token
        token = secrets.token_urlsafe(32)

        # Store token in DynamoDB with TTL
        try:
            mapping_table.put_item(
                Item={
                    "slack_user_id": f"pending_{token}",
                    "cognito_user_id": slack_user_id,  # Temporarily store Slack ID here
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                    "ttl": int((datetime.now() + timedelta(minutes=10)).timestamp()),
                }
            )
        except Exception as e:
            logger.error(f"Error storing token: {str(e)}")

        # Point to local frontend for development
        link_url = "http://localhost:3000/slack-link.html?token={}".format(token)

        return slack_response(
            {
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "🔗 *Link Your CloudOps Account*\n\nTo use CloudOps commands in Slack, you need to link your existing CloudOps account.",
                        },
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": "<{}|🔗 Click Here to Link Account>\n\n⏰ This secure link expires in 10 minutes.".format(
                                link_url
                            ),
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    "💡 You'll log in with your existing CloudOps "
                                    "email and password. No new account needed!"
                                ),
                            }
                        ],
                    },
                ],
            }
        )

    except Exception as e:
        logger.error(f"Register command error: {str(e)}")
        return slack_response(
            {
                "response_type": "ephemeral",
                "text": f"Error generating registration link: {str(e)}",
            }
        )


def get_infrastructure_status(cloudops_user_id):
    """Get overall infrastructure status"""
    try:
        # Get cost data (global, not user-specific)
        cost_data = get_current_costs()

        # Get drift status
        drift_count = get_drift_count(cloudops_user_id)

        # Get recent plans
        recent_plans = get_recent_plans(cloudops_user_id)

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📊 CloudOps Status Report"},
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*💰 Current Spend:*\n${cost_data.get('amount', '0.00')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*🔄 Drift Status:*\n{drift_count} repos need attention",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*📈 Recent Plans:*\n{len(recent_plans)} in last 24h",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*⏰ Last Updated:*\n{datetime.now().strftime('%H:%M UTC')}",
                    },
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Details"},
                        "url": "https://your-cloudops-url.com",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Run Scan"},
                        "action_id": "run_scan",
                    },
                ],
            },
        ]

        return slack_response({"response_type": "in_channel", "blocks": blocks})

    except Exception as e:
        logger.error(f"Status error: {str(e)}")
        return slack_response(
            {"response_type": "ephemeral", "text": f"Error getting status: {str(e)}"}
        )


def get_drift_status(user_id, repo=None):
    """Get drift status for repos"""
    try:
        if repo:
            # Get specific repo drift
            response = drift_configs_table.scan(
                FilterExpression="repo_name = :repo",
                ExpressionAttributeValues={":repo": repo},
            )
        else:
            # Get all user's drift configs
            response = drift_configs_table.scan(
                FilterExpression="user_id = :user_id",
                ExpressionAttributeValues={":user_id": user_id},
            )

        configs = response.get("Items", [])

        if not configs:
            return slack_response(
                {
                    "response_type": "ephemeral",
                    "text": "No drift monitoring configured. Set up monitoring in the CloudOps dashboard.",
                }
            )

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🔄 Drift Status{f' - {repo}' if repo else ''}",
                },
            }
        ]

        for config in configs[:5]:  # Limit to 5 repos
            last_scan = config.get("last_scan", {})
            drift_detected = last_scan.get("drift_detected", False)
            status_icon = "🚨" if drift_detected else "✅"
            status_text = "Drift detected" if drift_detected else "No drift"

            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{status_icon} *{config['repo_name']}*\n{status_text}",
                    },
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Scan Now"},
                        "action_id": f"scan_{config['config_id']}",
                    },
                }
            )

        return slack_response({"response_type": "in_channel", "blocks": blocks})

    except Exception as e:
        logger.error(f"Drift status error: {str(e)}")
        return slack_response(
            {
                "response_type": "ephemeral",
                "text": f"Error getting drift status: {str(e)}",
            }
        )


def get_cost_status(user_id, service=None):
    """Get cost status"""
    try:
        cost_data = get_current_costs()

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"💰 Cost Analysis{f' - {service}' if service else ''}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Current Month:*\n${cost_data.get('amount', '0.00')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Period:*\n{cost_data.get('period', 'Current month')}",
                    },
                ],
            },
        ]

        return slack_response({"response_type": "in_channel", "blocks": blocks})

    except Exception as e:
        logger.error(f"Cost status error: {str(e)}")
        return slack_response(
            {
                "response_type": "ephemeral",
                "text": f"Error getting cost status: {str(e)}",
            }
        )


def start_incident(user_id, title):
    """Start a new incident"""
    try:
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🚨 New Incident Created"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Title:* {title}\n*Created by:* <@{user_id}>\n*Status:* Active",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "High Severity"},
                        "style": "danger",
                        "action_id": "severity_high",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Medium Severity"},
                        "style": "primary",
                        "action_id": "severity_medium",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Low Severity"},
                        "action_id": "severity_low",
                    },
                ],
            },
        ]

        return slack_response({"response_type": "in_channel", "blocks": blocks})

    except Exception as e:
        logger.error(f"Incident creation error: {str(e)}")
        return slack_response(
            {"response_type": "ephemeral", "text": f"Error creating incident: {str(e)}"}
        )


def explain_terraform_plan(user_id, plan_id):
    """Explain a terraform plan"""
    try:
        # Get plan from DynamoDB
        response = plans_table.get_item(Key={"plan_id": plan_id})

        if "Item" not in response:
            return slack_response(
                {"response_type": "ephemeral", "text": f"Plan {plan_id} not found"}
            )

        plan = response["Item"]

        # Check if user owns this plan
        if plan.get("user_id") != user_id:
            return slack_response(
                {
                    "response_type": "ephemeral",
                    "text": "You don't have access to this plan",
                }
            )

        # Get AI explanation if available
        explanation = plan.get("ai_explanation", {})

        if not explanation:
            return slack_response(
                {
                    "response_type": "ephemeral",
                    "text": f"No AI explanation available for plan {plan_id}. Generate one in the dashboard first.",
                }
            )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🤖 Terraform Plan Explanation"},
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Repository:*\n{plan.get('repo_name', 'Unknown')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Risk Level:*\n{explanation.get('risk_level', 'Unknown')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Evaluated by:*\n{explanation.get('evaluated_by', 'Unknown')}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Changes:*\n{plan.get('changes_detected', 0)}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:*\n{explanation.get('summary', 'No summary available')}",
                },
            },
        ]

        if explanation.get("recommendations"):
            rec_text = "\n".join(
                [f"• {rec}" for rec in explanation["recommendations"][:3]]
            )
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Recommendations:*\n{rec_text}",
                    },
                }
            )

        return slack_response({"response_type": "in_channel", "blocks": blocks})

    except Exception as e:
        logger.error(f"Plan explanation error: {str(e)}")
        return slack_response(
            {"response_type": "ephemeral", "text": f"Error explaining plan: {str(e)}"}
        )


def search_documentation(query, user_id):
    """Search service documentation for answers"""
    try:
        # Simple keyword search in service docs
        response = service_docs_table.scan(
            FilterExpression="contains(#content, :query)",
            ExpressionAttributeNames={"#content": "content"},
            ExpressionAttributeValues={":query": query.lower()},
            Limit=3,
        )

        docs = response.get("Items", [])

        if not docs:
            return "I couldn't find documentation matching your query. Try uploading service docs in the CloudOps dashboard."

        # Use AI to generate response
        try:
            context = "\n".join([doc.get("content", "")[:500] for doc in docs])

            prompt = f"""Based on this documentation, answer the user's question: "{query}"

Documentation:
{context}

Provide a helpful, step-by-step answer. If you can't answer from the docs, say so."""

            response = bedrock.invoke_model(
                modelId="amazon.nova-lite-v1:0",
                body=json.dumps(
                    {
                        "messages": [{"role": "user", "content": [{"text": prompt}]}],
                        "inferenceConfig": {"maxTokens": 300},
                    }
                ),
            )

            result = json.loads(response["body"].read())
            return result["output"]["message"]["content"][0]["text"]

        except Exception:
            # Fallback to simple doc excerpt
            return f"Found in documentation: {docs[0].get('content', '')[:200]}..."

    except Exception as e:
        logger.error(f"Documentation search error: {str(e)}")
        return "Error searching documentation. Please try again."


def get_current_costs():
    """Get current AWS costs"""
    try:
        # Cost cache keys are formatted like: current_costs_2025-09_14
        from datetime import datetime

        now = datetime.now()

        # Try current hour first, then previous hours
        for hour_offset in range(0, 24):
            hour = (now.hour - hour_offset) % 24
            cache_key = f"current_costs_{now.strftime('%Y-%m')}_{hour:02d}"
            logger.info(f"Trying cost cache key: {cache_key}")

            try:
                response = cost_cache_table.get_item(Key={"cache_key": cache_key})

                if "Item" in response:
                    cost_item = response["Item"]
                    logger.info(f"Found cost data with key {cache_key}: {cost_item}")

                    # Parse the JSON data
                    if "data" in cost_item:
                        import json

                        cost_data = json.loads(cost_item["data"])
                        return {
                            "amount": f"{cost_data.get('total_cost', 0.00):.2f}",
                            "period": cost_data.get("period", "Current month"),
                        }
                    return cost_item
            except Exception as e:
                logger.info(f"Cache key {cache_key} not found: {str(e)}")
                continue

        logger.info("No cost data found in cache")
        return {"amount": "0.00", "period": "Current month"}

    except Exception as e:
        logger.error(f"Cost retrieval error: {str(e)}")
        return {"amount": "0.00", "period": "Error"}


def get_drift_count(user_id):
    """Get count of repos with drift"""
    try:
        logger.info(f"Getting drift count for user: {user_id}")
        response = drift_configs_table.scan(
            FilterExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        logger.info(f"Drift configs response: {response}")

        drift_count = 0
        for config in response.get("Items", []):
            if config.get("last_scan", {}).get("drift_detected"):
                drift_count += 1

        logger.info(f"Found {drift_count} repos with drift")
        return drift_count

    except Exception as e:
        logger.error(f"Error getting drift count: {str(e)}")
        return 0


def get_recent_plans(user_id):
    """Get recent terraform plans"""
    try:
        # Use the user-id-index to query by user_id
        from boto3.dynamodb.conditions import Key

        response = plans_table.query(
            IndexName="user-id-index",
            KeyConditionExpression=Key("user_id").eq(user_id),
            Limit=10,
            ScanIndexForward=False,
        )

        return response.get("Items", [])

    except Exception as e:
        logger.error(f"Error getting recent plans: {str(e)}")
        return []


def slack_response(data):
    """Format Slack response"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(data),
    }
