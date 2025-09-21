#!/bin/bash

# LocalStack initialization script
echo "Setting up CloudOps Assistant local environment..."

# Create DynamoDB tables
awslocal dynamodb create-table \
    --table-name cloudops-assistant-terraform-plans \
    --attribute-definitions AttributeName=plan_id,AttributeType=S AttributeName=user_id,AttributeType=S \
    --key-schema AttributeName=plan_id,KeyType=HASH \
    --global-secondary-indexes IndexName=user-id-index,KeySchema=[{AttributeName=user_id,KeyType=HASH}],Projection={ProjectionType=ALL},ProvisionedThroughput={ReadCapacityUnits=5,WriteCapacityUnits=5} \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

awslocal dynamodb create-table \
    --table-name cloudops-assistant-cost-cache \
    --attribute-definitions AttributeName=cache_key,AttributeType=S \
    --key-schema AttributeName=cache_key,KeyType=HASH \
    --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5

# Create Cognito User Pool
awslocal cognito-idp create-user-pool \
    --pool-name cloudops-assistant-users \
    --policies PasswordPolicy='{MinimumLength=8,RequireUppercase=true,RequireLowercase=true,RequireNumbers=true}' \
    --auto-verified-attributes email \
    --username-attributes email

# Create S3 bucket
awslocal s3 mb s3://cloudops-assistant-service-docs

echo "LocalStack setup complete!"
