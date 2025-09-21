# Local Development Guide

## Day 14: 100% AWS-Free Local Development

Run CloudOps Assistant completely locally using LocalStack - no AWS account required!

## Quick Start

### Prerequisites
- Docker Desktop
- Python 3.9+
- Git

### Option 1: Local Development with AI
```bash
make dev-start-ai
```

### Option 2: Basic Local Development
```bash
make dev-start
```

### Option 3: Manual Setup
```bash
# 1. Start LocalStack
make dev-start

# 2. In another terminal, start frontend
make dev-frontend
```

## What's Running

- **LocalStack**: http://localhost:4566 (AWS services)
- **API Server**: http://localhost:8080 (Backend APIs)
- **Frontend**: http://localhost:3000 (Web interface)
- **Ollama AI**: http://localhost:11434 (Local AI model)

## Local Features

✅ **Terraform Plan Processing**: Upload and analyze plans
✅ **Plan History**: Store and retrieve historical data
✅ **Cost Dashboard**: Mock cost data for development
✅ **Authentication**: Mock Cognito authentication
✅ **DynamoDB**: Local DynamoDB tables
✅ **S3**: Local S3 buckets
✅ **AI Features**: Local Ollama models (CodeLlama, Mistral)
✅ **AI Terraform Analysis**: Plan explanations and risk assessment
✅ **AI Postmortem Chat**: Interactive incident analysis

❌ **Real AWS Costs**: Uses mock data
❌ **GitHub Integration**: Limited functionality

## Development Workflow

1. **Start Environment**: `make dev-start-ai` (with AI) or `make dev-start` (basic)
2. **Make Changes**: Edit code in `backend/lambda/` or `frontend/`
3. **Test Changes**: API auto-reloads, refresh frontend
4. **Test AI**: `make dev-test-ai`
5. **Stop Environment**: `make dev-stop`

## AI Model Setup

The setup script automatically tries these models in order:
1. **codellama:7b-code** - Best for code analysis (~4GB)
2. **codellama:7b** - General code model (~4GB)
3. **llama2:7b-chat** - Good chat model (~4GB)
4. **mistral:7b** - Fast general model (~4GB)

First successful model will be used for AI features.

## Troubleshooting

**LocalStack not starting?**
```bash
make dev-clean  # Clean up containers
make dev-start  # Restart
```

**Port conflicts?**
- LocalStack: 4566
- API Server: 8080
- Frontend: 3000

**View logs:**
```bash
make dev-logs
```

**AI not working?**
```bash
# Setup AI model
make dev-setup-ai

# Test AI integration
make dev-test-ai

# Check Ollama status
curl http://localhost:11434/api/tags
```

## Mock Data

The local environment includes:
- Sample terraform plans
- Mock cost data ($125.43 total)
- Test user accounts
- Service documentation examples

Perfect for development and demos without AWS costs!
