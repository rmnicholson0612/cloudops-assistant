#!/bin/bash

# Exit on any error
set -e

# LocalStack initialization script
echo "Setting up CloudOps Assistant local environment..."

# Create DynamoDB tables
if ! awslocal dynamodb create-table \
    --table-name cloudops-assistant-terraform-plans \
    --attribute-definitions AttributeName=plan_id,AttributeType=S AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=plan_id,KeyType=HASH \
    --global-secondary-indexes IndexName=user-id-index,KeySchema=[{AttributeName=user_id,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5} \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5; then
    echo "Error: Failed to create terraform-plans table" >&2
    exit 1
fi

if ! awslocal dynamodb create-table \
    --table-name cloudops-assistant-cost-cache \
    --attribute-definitions AttributeName=cache_key,AttributeType=S \
    --key-schema AttributeName=cache_key,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5; then
    echo "Error: Failed to create cost-cache table" >&2
    exit 1
fi

# Create Cognito User Pool
if ! awslocal cognito-idp create-user-pool \
    --pool-name cloudops-assistant-users \
    --policies PasswordPolicy='{MinimumLength=8,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true}' \
    --auto-verified-attributes email \
    --username-attributes email; then
    echo "Error: Failed to create Cognito user pool" >&2
    exit 1
fi

# Create S3 bucket
if ! awslocal s3 mb s3://cloudops-assistant-service-docs; then
    echo "Error: Failed to create S3 bucket" >&2
    exit 1
fi

echo "LocalStack setup complete!"
