# 🤖 CloudOps Slack Bot Setup - Day 12

## Overview
The CloudOps Slack Bot brings infrastructure monitoring, AI-powered Q&A, and incident management directly into your Slack workspace.

## Features
- **Slash Commands**: `/cloudops status`, `/cloudops drift`, `/cloudops costs`
- **AI Q&A**: `@CloudOps "How do I restart the payment service?"`
- **Incident Management**: `/cloudops incident "Database timeout"`
- **Proactive Alerts**: Budget warnings, drift detection, cost spikes

## Setup Instructions

### 1. Create Slack App
1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "CloudOps Assistant"
4. Choose your workspace
5. Click "Create App"

### 2. Configure Bot Permissions
In your Slack app settings:

**OAuth & Permissions** → **Scopes**:
- `app_mentions:read` - Read mentions
- `chat:write` - Send messages
- `commands` - Use slash commands
- `users:read` - Read user info

### 3. Enable Events
**Event Subscriptions**:
- Enable Events: ON
- Request URL: `https://YOUR-API-GATEWAY-URL/Prod/slack/events`
- Subscribe to Bot Events:
  - `app_mention` - When bot is mentioned

### 4. Create Slash Commands
**Slash Commands** → **Create New Command**:
- Command: `/cloudops`
- Request URL: `https://YOUR-API-GATEWAY-URL/Prod/slack/commands`
- Short Description: "CloudOps infrastructure commands"
- Usage Hint: `status | drift [repo] | costs [service] | incident [title]`

### 5. Install App to Workspace
**Install App** → **Install to Workspace**
- Copy the **Bot User OAuth Token** (starts with `xoxb-`)

### 6. Get Signing Secret
**Basic Information** → **App Credentials**
- Copy the **Signing Secret**

### 7. Deploy with Slack Credentials
```bash
# Deploy with Slack tokens
sam deploy --stack-name cloudops-assistant \
  --parameter-overrides \
    SlackBotToken="xoxb-your-bot-token" \
    SlackSigningSecret="your-signing-secret" \
  --capabilities CAPABILITY_IAM
```

### 8. Update Slack URLs
After deployment, get your API Gateway URL from the stack outputs and update:
1. **Event Subscriptions** Request URL
2. **Slash Commands** Request URL

## Usage Examples

### Slash Commands
```
/cloudops help
/cloudops status
/cloudops drift user-api
/cloudops costs payment-service
/cloudops incident "Payment API timeout"
/cloudops explain plan-abc-123
```

### AI Mentions
```
@CloudOps payment service is returning 500 errors
@CloudOps how do I check database connections?
@CloudOps what changed in our infrastructure today?
```

### Interactive Responses
The bot provides rich interactive messages with:
- **Buttons**: Quick actions like "Run Scan", "View Details"
- **Status Cards**: Infrastructure health, costs, drift status
- **Threaded Conversations**: Incident response workflows

## Cost Estimate
- **Lambda**: ~$2/month (pay-per-request)
- **API Gateway**: ~$1/month (Slack webhooks)
- **DynamoDB**: ~$0.50/month (bot state/cache)
- **Total**: ~$3.50/month for unlimited Slack interactions

## Security Features
- **Request Verification**: Validates Slack signing secret
- **User Authentication**: Maps Slack users to CloudOps accounts
- **Permission Scoping**: Users only see their own data
- **Rate Limiting**: Prevents API abuse

## Troubleshooting

### Bot Not Responding
1. Check CloudWatch logs for the SlackBotFunction
2. Verify Request URLs in Slack app settings
3. Ensure bot token and signing secret are correct

### Permission Errors
1. Verify bot has required OAuth scopes
2. Check if bot is added to the channel
3. Ensure user has CloudOps account

### Slash Commands Not Working
1. Verify slash command Request URL
2. Check if command is properly registered
3. Look for Lambda timeout errors in CloudWatch

## Advanced Configuration

### Custom User Mapping
By default, the bot maps Slack user IDs to CloudOps user accounts. For custom mapping:

```python
# In slack_bot.py, modify get_user_id_from_slack()
def get_user_id_from_slack(slack_user_id):
    # Custom mapping logic here
    return cloudops_user_id
```

### Proactive Notifications
Enable proactive notifications by setting up EventBridge rules:

```yaml
# Add to template.yaml
SlackNotificationRule:
  Type: AWS::Events::Rule
  Properties:
    EventPattern:
      source: ["cloudops.drift"]
      detail-type: ["Drift Detected"]
    Targets:
      - Arn: !GetAtt SlackBotFunction.Arn
        Id: "SlackNotification"
```

## Next Steps
- **Day 13**: AI-powered PR reviews with Slack notifications
- **Day 18**: Smart alert routing based on service ownership
- **Future**: Multi-workspace support and advanced workflows

The Slack bot transforms your CloudOps experience from reactive dashboard checking to proactive, conversational infrastructure management! 🚀
