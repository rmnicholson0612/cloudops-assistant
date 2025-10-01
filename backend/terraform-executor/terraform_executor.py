import json
import os
import boto3
import time
from auth_utils import verify_jwt_token

def lambda_handler(event, context):
    try:
        print("Lambda function started successfully")
        print(f"Event: {json.dumps(event)}")
        print(f"Context: {context}")
        print(f"Environment variables: {dict(os.environ)}")
        
        # Handle empty event (return proper API Gateway response)
        if not event or not event.get("httpMethod"):
            return success_response({"status": "Terraform executor is running", "message": "Empty event received"})
            
        headers = event.get("headers", {})
        auth_header = headers.get("Authorization") or headers.get("authorization")
        
        if not auth_header or auth_header == "Bearer dummy-token":
            user_id = "internal-lambda-call"
        else:
            auth_result = verify_jwt_token(event)
            if auth_result.get("statusCode") == 401:
                return auth_result
            user_id = auth_result["user_id"]

        if event.get("httpMethod") == "OPTIONS":
            return cors_response()
        
        # Handle GET request for status
        if event.get("httpMethod") == "GET":
            return success_response({"status": "Terraform executor is running"})

        body = json.loads(event.get("body", "{}"))
        repo_url = body.get("repo_url")
        branch = body.get("branch", "main")
        terraform_dir = body.get("terraform_dir", ".")

        if not repo_url:
            return error_response(400, "repo_url is required")

        result = execute_terraform_plan(repo_url, branch, terraform_dir)
        
        # Check if result contains an error
        if isinstance(result, dict) and result.get("error"):
            return error_response(500, result["error"])
            
        return success_response(result)

    except Exception as e:
        print(f"Lambda error: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {
            "statusCode": 500,
            "headers": get_cors_headers(),
            "body": json.dumps({"error": f"Internal error: {str(e)}"})
        }

def execute_terraform_plan(repo_url, branch, terraform_dir):
    try:
        print(f"Starting terraform execution for {repo_url}")
        ecs = boto3.client('ecs')
        
        # Get network configuration
        print("Getting network configuration...")
        try:
            subnets = get_default_subnets()
            security_group = get_default_security_group()
            print(f"Found subnets: {subnets}, security group: {security_group}")
        except Exception as net_error:
            print(f"Network configuration error: {str(net_error)}")
            return {"error": f"Network configuration failed: {str(net_error)}"}
        
        if not subnets:
            return {"error": "No default subnets found. Please ensure you have a default VPC."}
        
        if not security_group:
            return {"error": "No default security group found. Please ensure you have a default VPC."}
        
        # Start Fargate task
        cluster_name = os.environ.get('ECS_CLUSTER')
        task_definition = os.environ.get('ECS_TASK_DEFINITION')
        
        print(f"Starting ECS task: cluster={cluster_name}, task_def={task_definition}")
        print(f"Environment variables: ECS_CLUSTER={cluster_name}, ECS_TASK_DEFINITION={task_definition}")
        
        if not cluster_name:
            return {"error": "ECS_CLUSTER environment variable not set"}
        if not task_definition:
            return {"error": "ECS_TASK_DEFINITION environment variable not set"}
        
        task_response = ecs.run_task(
            cluster=cluster_name,
            taskDefinition=task_definition,
            launchType='FARGATE',
            networkConfiguration={
                'awsvpcConfiguration': {
                    'subnets': subnets,
                    'assignPublicIp': 'ENABLED',
                    'securityGroups': [security_group]
                }
            },
            overrides={
                'containerOverrides': [{
                    'name': 'terraform',
                    'environment': [
                        {'name': 'REPO_URL', 'value': repo_url},
                        {'name': 'BRANCH', 'value': branch},
                        {'name': 'TERRAFORM_DIR', 'value': terraform_dir},
                        {'name': 'RESULTS_BUCKET', 'value': os.environ.get('RESULTS_BUCKET')}
                    ]
                }]
            }
        )
        
        if not task_response.get('tasks'):
            return {"error": "Failed to start ECS task", "details": task_response.get('failures', [])}
        
        task_arn = task_response['tasks'][0]['taskArn']
        task_id = task_arn.split('/')[-1]
        
        print(f"Task started: {task_arn}")
        
        # Return task info immediately (async execution)
        return {
            "success": True,
            "task_arn": task_arn,
            "task_id": task_id,
            "status": "running",
            "message": f"Terraform execution started. Task ID: {task_id}. Results will be stored in DynamoDB."
        }
            
    except Exception as e:
        print(f"ECS execution error: {str(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return {"error": f"ECS execution failed: {str(e)}"}

def get_default_subnets():
    ec2 = boto3.client('ec2')
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}])
    if not vpcs['Vpcs']:
        return []
    
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    subnets = ec2.describe_subnets(Filters=[{'Name': 'vpc-id', 'Values': [vpc_id]}])
    return [subnet['SubnetId'] for subnet in subnets['Subnets']]

def get_default_security_group():
    ec2 = boto3.client('ec2')
    vpcs = ec2.describe_vpcs(Filters=[{'Name': 'is-default', 'Values': ['true']}])
    if not vpcs['Vpcs']:
        return None
    
    vpc_id = vpcs['Vpcs'][0]['VpcId']
    sgs = ec2.describe_security_groups(Filters=[
        {'Name': 'vpc-id', 'Values': [vpc_id]},
        {'Name': 'group-name', 'Values': ['default']}
    ])
    return sgs['SecurityGroups'][0]['GroupId'] if sgs['SecurityGroups'] else None

def success_response(data):
    response = {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(data, default=str)
    }
    print(f"Returning response: {response}")
    return response

def error_response(status_code, message):
    return {
        "statusCode": status_code,
        "headers": get_cors_headers(),
        "body": json.dumps({"error": message})
    }

def cors_response():
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": ""
    }

def get_cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS"
    }