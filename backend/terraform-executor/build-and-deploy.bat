@echo off
REM Build and deploy terraform executor container for Windows

echo Building and deploying Terraform Executor container...

REM Get AWS account ID and region
for /f "tokens=*" %%i in ('aws sts get-caller-identity --query Account --output text') do set AWS_ACCOUNT_ID=%%i
for /f "tokens=*" %%i in ('aws configure get region') do set AWS_REGION=%%i
set ECR_REPO=cloudops-terraform-executor
set ECR_URI=%AWS_ACCOUNT_ID%.dkr.ecr.%AWS_REGION%.amazonaws.com/%ECR_REPO%

echo Account: %AWS_ACCOUNT_ID%
echo Region: %AWS_REGION%
echo ECR URI: %ECR_URI%

REM Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names %ECR_REPO% >nul 2>&1 || aws ecr create-repository --repository-name %ECR_REPO%

REM Get ECR login token
aws ecr get-login-password --region %AWS_REGION% | docker login --username AWS --password-stdin %ECR_URI%

REM Build Docker image
docker build -t %ECR_REPO% .

REM Tag image for ECR
docker tag %ECR_REPO%:latest %ECR_URI%:latest

REM Push to ECR
docker push %ECR_URI%:latest

echo Container deployed successfully to %ECR_URI%:latest
echo Run 'make deploy' to update the Lambda function
