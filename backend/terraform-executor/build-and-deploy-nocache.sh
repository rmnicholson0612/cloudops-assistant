#!/bin/bash
# Build and deploy terraform executor container for macOS/Linux

echo "Building and deploying Terraform Executor container..."

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region || echo "us-east-1")
ECR_REPO="cloudops-terraform-executor"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "Account: $AWS_ACCOUNT_ID"
echo "Region: $AWS_REGION"
echo "ECR URI: $ECR_URI"

# Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names $ECR_REPO >/dev/null 2>&1 || aws ecr create-repository --repository-name $ECR_REPO

# Get ECR login token
aws ecr get-login-password --region $AWS_REGION | podman login --username AWS --password-stdin $ECR_URI

# Build Docker image for x86_64 architecture (Lambda requirement)
podman build --no-cache --platform linux/amd64 -t $ECR_REPO .

# Tag image for ECR
podman tag $ECR_REPO:latest $ECR_URI:latest

# Push to ECR
podman push $ECR_URI:latest

echo "Container deployed successfully to $ECR_URI:latest"
echo "Run 'make deploy' to update the Lambda function"