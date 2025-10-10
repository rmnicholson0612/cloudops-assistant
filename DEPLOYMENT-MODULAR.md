# 🚀 Modular Deployment System

## 🎯 Quick Start

```bash
# Deploy core + drift + costs + security (recommended)
make deploy MODULES="drift costs security"

# Deploy just core + drift detection
make deploy MODULES="drift"

# Deploy everything
make deploy MODULES="drift costs security docs eol monitoring integrations incident-hub code-reviews"
```

## 📋 Available Modules

| Module | Description | Template |
|--------|-------------|----------|
| `drift` | Terraform drift detection | `template-drift.yaml` |
| `costs` | AWS cost dashboard | `template-costs.yaml` |
| `security` | Security compliance scanning | `template-security.yaml` |
| `docs` | Service documentation | `template-docs.yaml` |
| `eol` | End-of-life tracker | `template-eol.yaml` |
| `monitoring` | Resource discovery | `template-monitoring.yaml` |
| `integrations` | Slack/GitHub integrations | `template-integrations.yaml` |
| `incident-hub` | Postmortem generator | `template-incident-hub.yaml` |
| `code-reviews` | PR review automation | `template-code-reviews.yaml` |

## 🛠️ Deployment Commands

### Basic Deployments
```bash
# Core only (just auth)
make deploy-core

# Basic setup (drift + costs)
make deploy-basic

# Security focused (drift + costs + security)
make deploy-security

# Everything
make deploy-full
```

### Custom Deployments
```bash
# Just security scanning
make deploy MODULES="security"

# Drift + Security only
make deploy MODULES="drift security"

# Cost monitoring + Documentation
make deploy MODULES="costs docs"
```

### Module Management
```bash
# Add a module to existing deployment
make deploy-module MODULE=security

# Remove a module
make delete-module MODULE=security

# Update specific module
make deploy-module MODULE=drift
```

## 🏗️ Architecture

```
Core Stack (Always Required)
├── Cognito User Pool
├── API Gateway
└── Auth Handler Lambda

Module Stacks (Optional)
├── Drift Detection
│   ├── TerraformPlansTable
│   ├── DriftConfigTable
│   └── 4 Lambda Functions
├── Cost Dashboard
│   ├── CostCacheTable
│   └── CostAnalyzerFunction
└── Security Hub
    ├── SecurityFindingsTable
    └── SecurityScannerFunction
```

## 💰 Cost Optimization

| Deployment | Monthly Cost | Use Case |
|------------|--------------|----------|
| Core only | ~$1 | Testing/Development |
| Basic (drift+costs) | ~$3-5 | Small teams |
| Security (drift+costs+security) | ~$5-8 | Production ready |
| Full deployment | ~$15-25 | Enterprise |

## 🔧 Frontend Integration

The frontend automatically detects deployed modules and shows only available features:

```javascript
// Auto-generated in config.js
FEATURES: {
    DRIFT: true,     // Shows drift detection app
    COSTS: true,     // Shows cost dashboard app
    SECURITY: true,  // Shows security hub app
    DOCS: false,     // Hides documentation app
    // ... etc
}
```

## 📝 Examples

### Scenario 1: New Project
```bash
# Start with basics
make deploy MODULES="drift costs"

# Add security later
make deploy-module MODULE=security
```

### Scenario 2: Security Focus
```bash
# Security-first deployment
make deploy MODULES="security costs"
```

### Scenario 3: Full Platform
```bash
# Everything for large teams
make deploy-full
```

This modular system gives you complete control over what gets deployed while maintaining clean separation between features!
