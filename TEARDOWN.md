# 🔥 Teardown and Minimal Deployment Guide

## Step 1: Teardown Current Stack
```bash
# Delete current full stack
make teardown

# Wait for deletion to complete (check AWS Console)
aws cloudformation describe-stacks --stack-name cloudops-assistant
```

## Step 2: Deploy Minimal Stack
```bash
# Deploy only Core + Drift + Costs + Security
make deploy-minimal
```

## Step 3: Verify Deployment
```bash
# Check stack outputs
make outputs

# Test frontend
make serve-frontend
```

## What's Included in Minimal Stack:

### ✅ Core Module
- **Cognito User Pool** - Authentication
- **API Gateway** - REST API
- **Auth Handler Lambda** - JWT management

### ✅ Drift Detection Module
- **TerraformPlansTable** - Plan storage
- **DriftConfigTable** - Configuration storage
- **PlanProcessorFunction** - Plan upload/processing
- **PlanHistoryFunction** - Plan history/comparison
- **DriftConfigFunction** - Drift monitoring setup
- **RepoScannerFunction** - GitHub repository scanning

### ✅ Cost Dashboard Module
- **CostCacheTable** - Cost data caching
- **CostAnalyzerFunction** - AWS Cost Explorer integration

### ✅ Security Hub Module
- **SecurityFindingsTable** - Security scan results
- **SecurityScannerFunction** - Compliance scanning

## What's Excluded:
- ❌ Service Documentation (docs)
- ❌ EOL Tracker (eol)
- ❌ Resource Discovery (monitoring)
- ❌ Slack/GitHub Integrations (integrations)
- ❌ Incident Hub (incident-hub)
- ❌ Code Reviews (code-reviews)

## Frontend Feature Flags:
The frontend will automatically detect and show only:
- 🔒 Security Hub
- 📊 Cost Dashboard
- ⚠️ Drift Detection

All other app cards will be hidden automatically.
