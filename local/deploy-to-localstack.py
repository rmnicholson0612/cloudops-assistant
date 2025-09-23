#!/usr/bin/env python3
"""
Deploy SAM template to LocalStack automatically
Reads template.yaml and creates all resources in LocalStack
"""

import boto3
import yaml
import os
import re

# Custom YAML loader for CloudFormation functions
class CFLoader(yaml.SafeLoader):
    pass

def cf_constructor(loader, tag_suffix, node):
    """Handle CloudFormation intrinsic functions"""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    elif isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None

# Register CloudFormation function handlers
CFLoader.add_multi_constructor('!', cf_constructor)

def deploy_sam_to_localstack():
    """Deploy SAM template resources to LocalStack"""

    # Read SAM template with CloudFormation support
    template_path = os.path.join(os.path.dirname(__file__), '..', 'template.yaml')
    with open(template_path, 'r') as f:
        template = yaml.load(f, Loader=CFLoader)

    # LocalStack clients
    dynamodb = boto3.client('dynamodb', endpoint_url='http://localhost:4566', region_name='us-east-1')
    s3 = boto3.client('s3', endpoint_url='http://localhost:4566', region_name='us-east-1')
    cognito = boto3.client('cognito-idp', endpoint_url='http://localhost:4566', region_name='us-east-1')

    print("🚀 Deploying SAM template to LocalStack...")

    # Get existing resources
    existing_tables = dynamodb.list_tables()['TableNames']
    existing_buckets = [b['Name'] for b in s3.list_buckets()['Buckets']]

    # Deploy DynamoDB tables
    resources = template.get('Resources', {})
    for name, resource in resources.items():
        if resource['Type'] == 'AWS::DynamoDB::Table':
            props = resource['Properties']
            table_name = props['TableName']

            if table_name not in existing_tables:
                # Convert SAM properties to boto3 format
                create_params = {
                    'TableName': table_name,
                    'BillingMode': props.get('BillingMode', 'PAY_PER_REQUEST'),
                    'AttributeDefinitions': props['AttributeDefinitions'],
                    'KeySchema': props['KeySchema']
                }

                # Add GSI if present
                if 'GlobalSecondaryIndexes' in props:
                    create_params['GlobalSecondaryIndexes'] = props['GlobalSecondaryIndexes']

                dynamodb.create_table(**create_params)
                print(f"✅ Created DynamoDB table: {table_name}")
            else:
                print(f"⏭️  Table exists: {table_name}")

    # Deploy S3 buckets
    for name, resource in resources.items():
        if resource['Type'] == 'AWS::S3::Bucket':
            props = resource['Properties']
            bucket_name = props['BucketName']

            # Handle CloudFormation intrinsic functions for LocalStack
            if isinstance(bucket_name, dict) and '!Sub' in str(bucket_name):
                # Replace CloudFormation variables with LocalStack values
                bucket_name = 'cloudops-assistant-service-docs-123456789012'
            elif isinstance(bucket_name, str) and '${AWS::AccountId}' in bucket_name:
                bucket_name = bucket_name.replace('${AWS::AccountId}', '123456789012')

            if bucket_name not in existing_buckets:
                s3.create_bucket(Bucket=bucket_name)
                print(f"✅ Created S3 bucket: {bucket_name}")
            else:
                print(f"⏭️  Bucket exists: {bucket_name}")

    # Deploy Cognito User Pool
    for name, resource in resources.items():
        if resource['Type'] == 'AWS::Cognito::UserPool':
            props = resource['Properties']
            pool_name = props['UserPoolName']

            try:
                # Check if pool exists
                pools = cognito.list_user_pools(MaxResults=50)['UserPools']
                existing_pool = next((p for p in pools if p['Name'] == pool_name), None)

                if not existing_pool:
                    cognito.create_user_pool(
                        PoolName=pool_name,
                        AutoVerifiedAttributes=props.get('AutoVerifiedAttributes', []),
                        UsernameAttributes=props.get('UsernameAttributes', [])
                    )
                    print(f"✅ Created Cognito User Pool: {pool_name}")
                else:
                    print(f"⏭️  User Pool exists: {pool_name}")
            except Exception as e:
                print(f"⚠️  Cognito setup skipped: {e}")

    # Seed tables with sample data
    seed_sample_data(dynamodb)

    print("🎉 LocalStack deployment complete!")

def seed_sample_data(dynamodb):
    """Add sample data to LocalStack tables"""
    import uuid
    import time

    try:
        # Clean LocalStack environment - no seed data for testing

        print("✅ LocalStack tables created - no seed data")
    except Exception as e:
        print(f"⚠️  Seeding failed: {e}")

if __name__ == '__main__':
    deploy_sam_to_localstack()
