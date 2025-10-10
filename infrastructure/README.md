# 🏗️ Infrastructure Templates

## 📁 Template Structure

```
infrastructure/
├── template-full.yaml     # Complete CloudOps Assistant (all features)
├── template-core.yaml     # Core infrastructure (API Gateway, Cognito, Auth)
└── template-security.yaml # Security Hub module
```

## 🚀 Deployment Options

### Full Stack (Recommended for new deployments)
```bash
make deploy              # Deploy everything
make deploy-guided       # Interactive deployment
```

### Modular Deployment
```bash
make deploy-core         # Deploy core infrastructure first
make deploy-security     # Add Security Hub module
make deploy-modular      # Deploy core + security together
```

### Individual Modules
```bash
make delete-security     # Remove Security Hub only
```

## 🔧 Template Details

### Core Template (`template-core.yaml`)
- **Cognito User Pool** - Authentication
- **API Gateway** - REST API endpoints
- **Auth Handler Lambda** - JWT token management
- **Outputs** - UserPoolId, RestApiId for module integration

### Security Template (`template-security.yaml`)
- **SecurityFindingsTable** - DynamoDB for scan results
- **SecurityScannerFunction** - Compliance scanning Lambda
- **IAM Policies** - AWS service read permissions
- **API Routes** - `/security/*` endpoints

### Full Template (`template-full.yaml`)
- Everything from the original monolithic deployment
- All features in a single stack

## 💡 When to Use Each

- **Full Stack**: Simple deployment, all features needed
- **Core + Modules**: Cost optimization, selective features
- **Core Only**: Minimal setup, add features later
