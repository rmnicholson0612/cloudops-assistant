# CloudOps Assistant Architecture

## Overview
CloudOps Assistant is a serverless DevOps platform built on AWS, providing infrastructure monitoring, cost analysis, and automated quality pipelines.

## Architecture Evolution

### Day 6: Open Source Quality Pipeline
- **GitHub Actions Workflows**: Automated quality, security, and documentation checks
- **Pre-commit Hooks**: Local quality gates with Black, isort, flake8, bandit
- **Community Guidelines**: Issue templates, PR templates, contributing guidelines
- **Testing Framework**: Unit tests with pytest and coverage reporting
- **Security Scanning**: Bandit, Safety, TruffleHog for vulnerability detection
- **Documentation Automation**: README validation and badge updates

### Day 5: JWT Authentication
- **AWS Cognito User Pool**: Complete user management system
- **JWT Token Authentication**: All endpoints require valid JWT tokens
- **User Data Isolation**: All DynamoDB tables scoped by user_id
- **CORS Configuration**: Proper handling of preflight requests

### Days 1-4: Core Features
- **Terraform Plan Processing**: Real terraform plan analysis and drift detection
- **Cost Monitoring**: AWS Cost Explorer integration with caching
- **Budget Management**: Configurable budgets with SNS alerts
- **Plan History**: Historical terraform plan storage and comparison

## Current Architecture (Day 6)

### Frontend Layer
- **Technology**: Static HTML/CSS/JavaScript
- **Hosting**: Local development (S3 + CloudFront planned)
- **Authentication**: JWT token management in localStorage
- **Features**: Dashboard, cost analysis, plan management, user authentication

### API Layer
- **AWS API Gateway**: REST API with CORS enabled
- **Authentication**: JWT validation on all protected endpoints
- **Rate Limiting**: Built-in API Gateway throttling
- **Endpoints**: 15+ endpoints across authentication, plans, costs, budgets

### Compute Layer
- **6 Lambda Functions**: All using Python 3.11 runtime
  - AuthHandler: User registration/login (256MB, 30s)
  - PlanProcessor: Terraform plan analysis (512MB, 60s)
  - PlanHistory: Historical data retrieval (256MB, 30s)
  - CostAnalyzer: AWS cost analysis (256MB, 30s)
  - BudgetManager: Budget configuration (256MB, 30s)
  - RepoScanner: GitHub repository scanning (1024MB, 300s)

### Data Layer
- **DynamoDB Tables**: 4 tables with user isolation
  - cloudops-assistant-terraform-plans: Plan storage with TTL
  - cloudops-assistant-budget-config: Budget configurations
  - cloudops-assistant-cost-cache: Cost data caching (12h TTL)
  - (Cognito manages user data)

### Authentication Layer
- **AWS Cognito User Pool**: cloudops-assistant-users
- **Token Configuration**: 24h access tokens, 30-day refresh tokens
- **Security**: Email verification, password policies

### Quality Pipeline (Day 6)
- **GitHub Actions**: 3 workflows (quality, security, documentation)
- **Pre-commit Hooks**: Automated formatting and linting
- **Testing**: Unit tests with pytest and coverage
- **Security**: Vulnerability scanning and secrets detection
- **Documentation**: Automated validation and updates

## Security Features

### Authentication & Authorization
- JWT-based authentication on all endpoints
- User data isolation via user_id scoping
- Cognito-managed user sessions
- Input sanitization and validation

### Data Protection
- DynamoDB encryption at rest (SSE)
- TTL-based data expiration
- NoSQL injection prevention
- Secure error handling

### Network Security
- CORS configuration (needs improvement)
- API Gateway rate limiting
- VPC isolation (planned)

## Cost Optimization

### Current Costs (Estimated)
- **Lambda**: ~$2-5/month (free tier covers most usage)
- **DynamoDB**: ~$1-3/month (on-demand pricing)
- **API Gateway**: ~$1-2/month (free tier covers development)
- **Cognito**: Free tier covers expected usage
- **Total**: $5-15/month for moderate usage

### Optimization Strategies
- 12-hour cost data caching
- DynamoDB TTL for automatic cleanup
- Efficient Lambda memory allocation
- Pay-per-request pricing models

## Deployment

### Infrastructure as Code
- **AWS SAM**: Complete serverless application model
- **CloudFormation**: Automated resource provisioning
- **GitHub Actions**: Automated quality pipeline

### Development Workflow
1. Local development with pre-commit hooks
2. GitHub Actions quality/security checks
3. Manual SAM deployment (automated deployment planned)
4. Monitoring via CloudWatch logs

## Monitoring & Observability

### Current Monitoring
- CloudWatch Logs for all Lambda functions
- DynamoDB metrics
- API Gateway request/error metrics
- Cost tracking via Cost Explorer

### Planned Enhancements (Week 3)
- Custom dashboards
- Alerting system
- Performance monitoring
- Uptime tracking

## Future Architecture (Days 7-30)

### Week 2: AI Layer
- AWS Bedrock integration
- Terraform plan explanation
- Automated documentation
- Intelligent alerting

### Week 3: Observability
- Custom monitoring dashboards
- Uptime monitoring
- Performance analytics
- Public status page

### Week 4: Advanced Features
- Multi-tenant architecture
- Role-based access control
- Advanced integrations
- Production hardening

## Technology Stack

### Backend
- **Runtime**: Python 3.11
- **Framework**: AWS Lambda + API Gateway
- **Database**: DynamoDB
- **Authentication**: AWS Cognito
- **Caching**: DynamoDB with TTL

### Frontend
- **Technology**: Vanilla JavaScript (React planned)
- **Styling**: CSS3 with modern features
- **Build**: Static files (Vite planned)

### DevOps
- **IaC**: AWS SAM + CloudFormation
- **CI/CD**: GitHub Actions
- **Quality**: Pre-commit hooks, automated testing
- **Security**: Bandit, Safety, TruffleHog

### External Services
- **AWS Cost Explorer**: Cost data retrieval
- **GitHub API**: Repository scanning
- **SNS**: Budget alert notifications

## Development Guidelines

### Code Quality
- Black code formatting
- isort import sorting
- flake8 linting
- pylint code analysis
- 80%+ test coverage

### Security
- Input sanitization on all endpoints
- JWT validation
- NoSQL injection prevention
- Secrets scanning
- Dependency vulnerability checks

### Performance
- Efficient DynamoDB queries
- Lambda cold start optimization
- Cost data caching
- Resource right-sizing

This architecture provides a solid foundation for a production-ready DevOps platform while maintaining cost efficiency and security best practices.