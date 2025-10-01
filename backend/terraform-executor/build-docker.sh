#!/bin/bash
# Build and deploy terraform executor container using Docker

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
aws ecr describe-repositories --repository-names $ECR_REPO --region $AWS_REGION >/dev/null 2>&1 || {
    echo "Creating ECR repository..."
    aws ecr create-repository --repository-name $ECR_REPO --region $AWS_REGION
}

# Get ECR login token
echo "Logging into ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI

# Build Docker image for x86_64 architecture (ECS Fargate requirement)
echo "Building Docker image..."
docker build --platform linux/amd64 -t $ECR_REPO .

# Tag image for ECR
echo "Tagging image..."
docker tag $ECR_REPO:latest $ECR_URI:latest

# Push to ECR
echo "Pushing to ECR..."
docker push $ECR_URI:latest

echo "Container deployed successfully to $ECR_URI:latest"
echo "You can now deploy the CloudFormation stack with 'sam deploy'"