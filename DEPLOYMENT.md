# 🚀 Modular Deployment Guide

CloudOps Assistant now supports modular deployment, allowing you to deploy only the features you need.

## 📋 Architecture Overview

### Core Stack (Required)
- **API Gateway**: Central REST API
- **Cognito**: User authentication
- **Auth Handler**: JWT token management

### Optional Modules
- **Security Hub**: Compliance scanning and security findings
- **Drift Detection**: Terraform plan monitoring
- **Cost Analysis**: AWS cost tracking and budgets
- **Service Documentation**: RAG-powered docs management
- **EOL Tracker**: End-of-life technology monitoring

## 🏗️ Deployment Options

### Option 1: Full Stack (Current Default)
```bash
# Deploy everything at once
make deploy
```

### Option 2: Modular Deployment

#### Step 1: Deploy Core Stack
```bash
# Deploy core infrastructure first
make deploy
```

#### Step 2: Deploy Security Hub Module
```bash
# Deploy Security Hub independently
make deploy-security

# Or with guided setup
make deploy-security-guided
```

#### Step 3: Remove Security Hub (if needed)
```bash
# Remove Security Hub module only
make delete-security
```

## 🔧 Security Hub Resources

The Security Hub module includes:

### DynamoDB Table
- **Name**: `cloudops-assistant-security-findings-{environment}`
- **Purpose**: Store security scan results and compliance findings
- **TTL**: 30 days automatic cleanup

### Lambda Function
- **Name**: `SecurityScannerFunction`
- **Memory**: 1024 MB
- **Timeout**: 15 minutes
- **Runtime**: Python 3.13

### IAM Permissions
- **EC2**: Describe instances, security groups, VPCs
- **S3**: List buckets, get bucket policies
- **IAM**: List users, roles, policies
- **RDS**: Describe DB instances
- **CloudTrail**: Describe trails and status
- **Config**: Describe configuration recorders
- **CloudWatch**: Describe alarms
- **KMS**: List and describe keys

### API Endpoints
- `POST /security/scan` - Run security compliance scan
- `GET /security/findings` - Get scan results
- `GET /security/compliance` - Get compliance summary
- `GET /security/compliance/rules` - Get compliance rules
- `GET /security/accounts` - Get account security summary

## 🎯 Benefits of Modular Deployment

1. **Cost Optimization**: Deploy only needed features
2. **Faster Deployments**: Update individual modules
3. **Easier Testing**: Test modules in isolation
4. **Better Organization**: Clear separation of concerns
5. **Flexible Scaling**: Scale modules independently

## 📊 Cost Comparison

### Full Stack
- ~15-20 Lambda functions
- ~10-12 DynamoDB tables
- Estimated cost: $10-25/month

### Core + Security Hub Only
- ~3 Lambda functions
- ~2 DynamoDB tables
- Estimated cost: $2-5/month

## 🔄 Migration Path

### From Full Stack to Modular

1. **Backup Data** (if needed)
2. **Deploy Security Module**:
   ```bash
   make deploy-security
   ```
3. **Verify Security Hub Works**
4. **Remove from Main Stack** (future update)

### Adding More Modules

Future modules will follow the same pattern:
```bash
make deploy-drift      # Drift detection module
make deploy-cost       # Cost analysis module
make deploy-docs       # Service documentation module
```

## 🚨 Important Notes

- **Core stack must be deployed first** - other modules depend on it
- **Environment consistency** - use same environment across modules
- **API Gateway integration** - modules attach to the core API Gateway
- **Cognito integration** - all modules use the same user pool

## 🔍 Troubleshooting

### Module Deployment Fails
```bash
# Check core stack outputs
aws cloudformation describe-stacks --stack-name cloudops-assistant-core-dev

# Validate Security template
make -f Makefile-security validate-security
```

### API Integration Issues
```bash
# Verify API Gateway has correct permissions
aws apigateway get-rest-apis

# Check Lambda function integration
aws lambda list-functions --query "Functions[?contains(FunctionName, 'Security')]"
```

This modular approach gives you complete control over your CloudOps Assistant deployment while maintaining the flexibility to scale as needed.
