# 🚀 CloudOps Assistant - Complete Deployment Guide

## Prerequisites

1. **AWS CLI configured** with appropriate permissions
2. **SAM CLI installed** (`pip install aws-sam-cli`)
3. **Python 3.9+** installed
4. **Git** for cloning the repository

## Required AWS Permissions

Your AWS user/role needs these permissions:
- CloudFormation (full access)
- Lambda (full access)
- API Gateway (full access)
- DynamoDB (full access)
- Cognito (full access)
- IAM (create/attach roles)
- S3 (for SAM deployment artifacts)

## Complete From-Scratch Deployment

### 1. Clone and Setup
```bash
git clone https://github.com/rmnicholson0612/cloudops-assistant
cd cloudops-assistant
```

### 2. Bootstrap Environment
```bash
# This will:
# - Create environment files from templates
# - Install Python dependencies
# - Validate AWS configuration
# - Run quality checks
make bootstrap
```

### 3. Configure Environment
Edit the generated environment files:

**`backend/.env`:**
```bash
ENVIRONMENT=prod
AWS_REGION=us-east-1
STACK_NAME=cloudops-assistant
BEDROCK_MODEL=nova-lite
BEDROCK_COMPLEX_MODEL=nova-lite
BEDROCK_SIMPLE_MODEL=nova-lite
GITHUB_TOKEN=ghp_your_token_here  # Optional: for private repos
```

**`frontend/.env`:**
```bash
VITE_APP_NAME=CloudOps Assistant
VITE_VERSION=1.0.0
VITE_ENVIRONMENT=production
VITE_ENABLE_DRIFT_DETECTION=true
VITE_ENABLE_COST_DASHBOARD=true
VITE_ENABLE_AI_FEATURES=true
```

### 4. Deploy Infrastructure
```bash
# First-time deployment (guided setup)
make deploy-guided

# Or automated deployment
make deploy
```

### 5. Verify Deployment
```bash
# Check stack outputs
make outputs

# Test API endpoints
make test-api
```

### 6. Access Application
1. Open `frontend/index.html` in your browser
2. Register a new account using the Cognito sign-up
3. Verify your email address
4. Login and start using the platform

## Environment-Specific Deployments

### Development Environment
```bash
# Edit backend/.env to set ENVIRONMENT=dev
make deploy-dev
```

### Staging Environment
```bash
make deploy-staging
```

### Production Environment
```bash
make deploy-prod
```

## Troubleshooting

### Common Issues

**1. AWS CLI not configured**
```bash
aws configure
# Enter your Access Key ID, Secret Access Key, Region, and Output format
```

**2. Insufficient permissions**
- Ensure your AWS user has the required permissions listed above
- Check CloudTrail logs for specific permission denials

**3. Stack already exists**
```bash
# Delete existing stack
make teardown
# Then redeploy
make deploy
```

**4. Frontend config not updating**
```bash
# Manually regenerate frontend config
make update-config
```

### Validation Commands
```bash
# Validate SAM template
make validate

# Run all quality checks
make quality

# Check environment setup
make check-env
```

## Cost Optimization

The stack is designed to run on AWS Free Tier:
- **Lambda**: 1M requests/month free
- **DynamoDB**: 25GB storage free
- **API Gateway**: 1M requests/month free
- **Cognito**: 50,000 MAUs free

**Estimated monthly cost for moderate usage: $5-15**

## Security Considerations

1. **Environment files** contain sensitive data - never commit them
2. **Cognito User Pool** handles authentication - no passwords stored
3. **DynamoDB encryption** enabled by default
4. **API Gateway** has CORS configured for JWT tokens
5. **Lambda functions** have minimal IAM permissions

## Cleanup

To completely remove the stack:
```bash
make teardown
```

This will delete all AWS resources created by the deployment.
