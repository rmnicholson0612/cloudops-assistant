#!/bin/bash

# Build and deploy terraform executor container
set -e

# Get AWS account ID and region
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION=$(aws configure get region)
ECR_REPO="cloudops-terraform-executor"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

echo "Building and deploying Terraform Executor container..."
echo "Account: ${AWS_ACCOUNT_ID}"
echo "Region: ${AWS_REGION}"
echo "ECR URI: ${ECR_URI}"

# Create ECR repository if it doesn't exist
aws ecr describe-repositories --repository-names ${ECR_REPO} 2>/dev/null || \
aws ecr create-repository --repository-name ${ECR_REPO}

# Get ECR login token
aws ecr get-login-password --region ${AWS_REGION} | docker login --username AWS --password-stdin ${ECR_URI}

# Build Docker image
docker build -t ${ECR_REPO} .

# Tag image for ECR
docker tag ${ECR_REPO}:latest ${ECR_URI}:latest

# Push to ECR
docker push ${ECR_URI}:latest

echo "Container deployed successfully to ${ECR_URI}:latest"
echo "Run 'make deploy' to update the Lambda function"
