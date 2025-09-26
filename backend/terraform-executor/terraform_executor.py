import json
import os
import subprocess
import tempfile
import shutil
from auth_utils import verify_jwt_token

def lambda_handler(event, context):
    try:
        # Verify authentication
        auth_result = verify_jwt_token(event)
        if auth_result.get("statusCode") == 401:
            return auth_result

        user_id = auth_result["user_id"]

        # Handle CORS preflight
        if event.get("httpMethod") == "OPTIONS":
            return cors_response()

        # Parse request
        body = json.loads(event.get("body", "{}"))
        repo_url = body.get("repo_url")
        branch = body.get("branch", "main")
        terraform_dir = body.get("terraform_dir", ".")

        if not repo_url:
            return error_response(400, "repo_url is required")

        # Execute terraform plan
        result = execute_terraform_plan(repo_url, branch, terraform_dir)

        return success_response(result)

    except Exception as e:
        return error_response(500, f"Internal error: {str(e)}")

def execute_terraform_plan(repo_url, branch, terraform_dir):
    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            # Clone repository
            clone_cmd = ["git", "clone", "-b", branch, repo_url, temp_dir]
            subprocess.run(clone_cmd, check=True, capture_output=True, text=True)

            # Change to terraform directory
            tf_path = os.path.join(temp_dir, terraform_dir)
            if not os.path.exists(tf_path):
                return {"error": f"Terraform directory '{terraform_dir}' not found"}

            # Initialize terraform
            init_result = subprocess.run(
                ["terraform", "init"],
                cwd=tf_path,
                capture_output=True,
                text=True,
                timeout=300
            )

            if init_result.returncode != 0:
                return {
                    "error": "Terraform init failed",
                    "stderr": init_result.stderr,
                    "stdout": init_result.stdout
                }

            # Run terraform plan
            plan_result = subprocess.run(
                ["terraform", "plan", "-no-color"],
                cwd=tf_path,
                capture_output=True,
                text=True,
                timeout=300
            )

            return {
                "success": plan_result.returncode == 0,
                "stdout": plan_result.stdout,
                "stderr": plan_result.stderr,
                "returncode": plan_result.returncode
            }

        except subprocess.TimeoutExpired:
            return {"error": "Terraform execution timed out"}
        except subprocess.CalledProcessError as e:
            return {"error": f"Command failed: {e}"}
        except Exception as e:
            return {"error": f"Execution error: {str(e)}"}

def success_response(data):
    return {
        "statusCode": 200,
        "headers": get_cors_headers(),
        "body": json.dumps(data, default=str)
    }

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
