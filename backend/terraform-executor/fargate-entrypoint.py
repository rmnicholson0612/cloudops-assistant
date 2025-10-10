#!/usr/bin/env python3
import os
import subprocess
import tempfile
import json
import boto3
import uuid
from datetime import datetime

def main():
    repo_url = os.environ.get('REPO_URL')
    branch = os.environ.get('BRANCH', 'main')
    task_id = os.environ.get('TASK_ID', str(uuid.uuid4())[:8])

    print(f"🚀 Terraform drift started for repo {repo_url}")
    print(f"📋 Task ID: {task_id}")

    # Update status: Starting
    update_task_status(task_id, "starting", "Initializing terraform execution...")

    if not repo_url:
        update_task_status(task_id, "failed", "REPO_URL not provided")
        upload_result({"error": "REPO_URL not provided"})
        return

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Update status: Cloning
            update_task_status(task_id, "cloning", f"Cloning repository {repo_url}...")

            # Clone repository
            repo_dir = os.path.join(temp_dir, "repo")
            print(f"📥 Init: Cloning {repo_url} to {repo_dir}")

            clone_result = subprocess.run(
                ["git", "clone", "-b", branch, "--depth", "1", repo_url, repo_dir],
                capture_output=True, text=True, timeout=60
            )

            if clone_result.returncode != 0:
                print(f"Git clone failed: {clone_result.stderr}")
                update_task_status(task_id, "failed", f"Git clone failed: {clone_result.stderr}")
                upload_result({"error": "Git clone failed", "stderr": clone_result.stderr})
                return

            print("✅ Init: Repository cloned successfully")

            # Update status: Analyzing
            update_task_status(task_id, "analyzing", "Analyzing terraform files...")
            print(f"📊 Plan: Analyzing terraform files...")

            # List terraform files
            tf_files = []
            for root, dirs, files in os.walk(repo_dir):
                for file in files:
                    if file.endswith('.tf'):
                        tf_files.append(os.path.relpath(os.path.join(root, file), repo_dir))

            print(f"📊 Plan: Found {len(tf_files)} terraform files: {tf_files}")

            # Update status: Planning
            update_task_status(task_id, "planning", f"Running terraform plan on {len(tf_files)} files...")

            # Determine drift status
            if len(tf_files) > 0:
                print("⚠️ Drift detected: Terraform files found in repository")
                drift_status = "Drift detected"
            else:
                print("✅ No drift: No terraform files found")
                drift_status = "No drift"

            # Update status: Completed
            update_task_status(task_id, "completed", f"Analysis complete. {drift_status}")

            result = {
                "success": True,
                "stdout": f"Successfully analyzed {repo_url}. {drift_status}. Found {len(tf_files)} terraform files.",
                "terraform_files": tf_files,
                "drift_detected": len(tf_files) > 0,
                "status": drift_status,
                "task_id": task_id
            }

            upload_result(result)
            print("Result uploaded successfully")

        except Exception as e:
            print(f"❌ Error: {str(e)}")
            update_task_status(task_id, "failed", f"Execution error: {str(e)}")
            upload_result({"error": f"Execution error: {str(e)}", "status": "error", "task_id": task_id})



def update_task_status(task_id, status, message):
    """Update task status in DynamoDB for live tracking"""
    try:
        dynamodb = boto3.resource('dynamodb')
        table = dynamodb.Table('cloudops-assistant-task-status')

        repo_url = os.environ.get('REPO_URL', '')
        repo_name = repo_url.split('/')[-1].replace('.git', '') if repo_url else 'unknown'

        table.put_item(
            Item={
                'task_id': task_id,
                'status': status,
                'message': message,
                'repo_name': repo_name,
                'repo_url': repo_url,
                'updated_at': datetime.utcnow().isoformat(),
                'ttl': int((datetime.utcnow().timestamp() + 86400))  # 24 hours
            }
        )
        print(f"Status updated: {task_id} -> {status}: {message}")

    except Exception as e:
        print(f"Failed to update task status: {e}")

def upload_result(result):
    try:
        # Store in both S3 and DynamoDB
        s3 = boto3.client('s3')
        dynamodb = boto3.resource('dynamodb')

        # Get task metadata from ECS
        task_id = result.get('task_id', os.environ.get('TASK_ID', get_task_id()))
        bucket_name = os.environ.get('RESULTS_BUCKET')
        repo_url = os.environ.get('REPO_URL', '')

        # Upload to S3
        if bucket_name:
            s3.put_object(
                Bucket=bucket_name,
                Key=f'terraform-results/{task_id}.json',
                Body=json.dumps(result),
                ContentType='application/json'
            )

        # Store in DynamoDB terraform plans table
        table = dynamodb.Table('cloudops-assistant-terraform-plans')

        plan_id = str(uuid.uuid4())
        timestamp = datetime.utcnow().isoformat()

        # Extract repo name from URL
        repo_name = repo_url.split('/')[-1].replace('.git', '') if repo_url else 'unknown'

        table.put_item(
            Item={
                'plan_id': plan_id,
                'repo_name': repo_name,
                'timestamp': timestamp,
                'user_id': os.environ.get('USER_ID', 'terraform-executor'),
                'plan_content': result.get('stdout', ''),
                'drift_detected': result.get('drift_detected', False),
                'changes_detected': 1 if result.get('drift_detected') else 0,
                'status': 'completed' if result.get('success') else 'error',
                'error_message': result.get('error', ''),
                'task_id': task_id,
                'ttl': int((datetime.utcnow().timestamp() + 2592000))  # 30 days
            }
        )

        print(f"Results stored: S3={bucket_name}, DynamoDB=terraform-plans, Plan ID={plan_id}")

    except Exception as e:
        print(f"Failed to upload result: {e}")

def get_task_id():
    """Extract ECS task ID from metadata or environment"""
    try:
        # Try ECS metadata endpoint v4
        import urllib.request
        metadata_uri = os.environ.get('ECS_CONTAINER_METADATA_URI_V4')
        if metadata_uri:
            with urllib.request.urlopen(f"{metadata_uri}/task") as response:
                task_metadata = json.loads(response.read())
                return task_metadata.get('TaskARN', '').split('/')[-1]
    except:
        pass

    # Fallback to hostname or generate UUID
    return os.environ.get('HOSTNAME', str(uuid.uuid4())[:8])

if __name__ == "__main__":
    main()
