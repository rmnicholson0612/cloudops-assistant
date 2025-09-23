import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def get_cors_headers():
    """Get standardized CORS headers for JWT authentication"""
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Amz-Date,X-Api-Key,X-Amz-Security-Token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }


def success_response(data):
    """Return standardized success response"""
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json", **get_cors_headers()},
        "body": json.dumps(data, default=str),
    }


def error_response(status_code, message):
    """Return standardized error response"""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json", **get_cors_headers()},
        "body": json.dumps({"error": message}),
    }


def sanitize_input(input_str):
    """Sanitize input to prevent injection attacks"""
    if not isinstance(input_str, str):
        return str(input_str)
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[<>"\\;{}$]', "", input_str)
    return sanitized.strip()[:255]  # Limit length


def lambda_handler(event, context):
    """Handle service documentation upload and search requests"""
    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "GET")

        # Handle OPTIONS for CORS
        if method == "OPTIONS":
            return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}

        # Extract user_id from JWT token
        user_id = extract_user_id(event)
        if not user_id:
            return error_response(401, "Unauthorized")

        if path == "/docs/register" and method == "POST":
            return register_service(event, user_id)
        elif path == "/docs/upload" and method == "POST":
            return handle_upload(event, user_id)
        elif path == "/docs/search" and method == "POST":
            return handle_search(event, user_id)
        elif path == "/docs/list" and method == "GET":
            return list_documents(user_id)
        elif path == "/docs/services" and method == "GET":
            return list_available_services(user_id)
        elif path == "/docs/get" and method == "POST":
            return get_document(event, user_id)
        elif path == "/docs/delete" and method == "DELETE":
            return delete_document(event, user_id)
        elif path == "/docs/get" and method == "OPTIONS":
            return {"statusCode": 200, "headers": get_cors_headers(), "body": ""}
        else:
            return error_response(404, "Not found")

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return error_response(500, str(e))


def extract_user_id(event):
    """Extract user ID from JWT token"""
    try:
        auth_header = event.get("headers", {}).get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header.replace("Bearer ", "")
        payload = token.split(".")[1]
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))
        return decoded.get("sub")
    except Exception:
        return None


def register_service(event, user_id):
    """Register a service from GitHub repo scan"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        service_owner = sanitize_input(body["service_owner"])
        github_repo = sanitize_input(body["github_repo"])

        if not all([service_name, service_owner, github_repo]):
            return error_response(400, "Missing required fields")

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

        # Register service metadata
        table.put_item(
            Item={
                "service_name": service_name,
                "doc_name": "_service_metadata",
                "s3_key": f"shared/{service_name}/_metadata",
                "service_owner": service_owner,
                "github_repo": github_repo,
                "upload_date": datetime.now(timezone.utc).isoformat(),
                "file_size": 0,
                "content_preview": f"Service: {service_name}, Owner: {service_owner}, Repo: {github_repo}",
                "registered_by": user_id,
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=365)).timestamp()
                ),
            }
        )

        return success_response(
            {
                "message": "Service registered successfully",
                "service_name": service_name,
            }
        )

    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        return error_response(500, str(e))


def list_available_services(user_id):
    """List services available from GitHub repo scans"""
    try:
        # Get terraform plans to extract repo names
        dynamodb = boto3.resource("dynamodb")
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        # Sanitize user_id to prevent injection
        safe_user_id = str(user_id).strip()[:100] if user_id else ""
        if not safe_user_id:
            return error_response(400, "Invalid user ID")

        try:
            from boto3.dynamodb.conditions import Key

            response = plans_table.query(
                IndexName="user-id-index",
                KeyConditionExpression=Key("user_id").eq(safe_user_id),
            )
        except Exception as db_error:
            logger.error(f"DynamoDB query failed: {str(db_error)}")
            return error_response(500, "Failed to retrieve services")

        # Extract unique repo names
        repos = set()
        for plan in response.get("Items", []):
            repo_name = plan.get("repo_name")
            if repo_name:
                repos.add(repo_name)

        # Convert to service format
        available_services = []
        for repo in repos:
            available_services.append(
                {
                    "service_name": repo,
                    "github_repo": f"https://github.com/user/{repo}",  # You can enhance this
                    "suggested_owner": "DevOps Team",  # Default suggestion
                }
            )

        return success_response({"available_services": available_services})

    except Exception as e:
        logger.error(f"List services error: {str(e)}")
        return error_response(500, str(e))


def handle_upload(event, user_id):
    """Handle document upload"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])
        content = body["content"]  # Don't sanitize content as it's document text

        if not all([service_name, doc_name, content]):
            return error_response(400, "Missing required fields")

        s3 = boto3.client("s3")
        bucket = "cloudops-assistant-service-docs"
        s3_key = f"shared/{service_name}/{doc_name}"

        s3.put_object(
            Bucket=bucket, Key=s3_key, Body=content, ContentType="text/markdown"
        )

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

        # Sanitize user_id before storing
        safe_user_id = str(user_id).strip()[:100] if user_id else ""
        if not safe_user_id:
            return error_response(400, "Invalid user ID")

        table.put_item(
            Item={
                "service_name": service_name,
                "doc_name": doc_name,
                "s3_key": s3_key,
                "upload_date": datetime.now(timezone.utc).isoformat(),
                "file_size": len(content),
                "content_preview": (
                    content[:200] + "..." if len(content) > 200 else content
                ),
                "uploaded_by": safe_user_id,
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=90)).timestamp()
                ),
            }
        )

        return success_response(
            {
                "message": "Document uploaded successfully",
                "service_name": service_name,
                "doc_name": doc_name,
            }
        )

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return error_response(500, str(e))


def handle_search(event, user_id):
    """Handle documentation search with AI"""
    try:
        body = json.loads(event["body"])
        raw_query = body["query"]

        if not raw_query:
            return error_response(400, "Query is required")

        # Sanitize query to prevent NoSQL injection
        query = sanitize_input(raw_query)

        docs = get_all_documents()
        relevant_docs = find_relevant_docs(query, docs)
        ai_response = generate_ai_response(query, relevant_docs)

        return success_response(
            {
                "query": query,
                "answer": ai_response["answer"],
                "sources": ai_response["sources"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return error_response(500, str(e))


def list_documents(user_id):
    """List all documents grouped by service"""
    try:
        docs = get_all_documents()

        services = {}
        for doc in docs:
            service_name = doc["service_name"]
            if service_name not in services:
                services[service_name] = []
            try:
                file_size_raw = doc.get("file_size", 0)
                if file_size_raw is None:
                    file_size = 0
                elif isinstance(file_size_raw, (int, float)):
                    file_size = int(file_size_raw)
                else:
                    file_size = int(str(file_size_raw))
            except (ValueError, TypeError, AttributeError):
                logger.warning("Invalid file_size value detected, defaulting to 0")
                file_size = 0

            services[service_name].append(
                {
                    "doc_name": doc["doc_name"],
                    "upload_date": doc["upload_date"],
                    "file_size": file_size,
                }
            )

        return success_response({"services": services, "total_documents": len(docs)})

    except Exception as e:
        logger.error(f"List error: {str(e)}")
        return error_response(500, str(e))


def get_all_documents():
    """Get all documents for all users"""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

        # Use scan with projection to limit data exposure
        response = table.scan(
            ProjectionExpression="service_name, doc_name, upload_date, file_size, content_preview"
        )

        return response.get("Items", [])
    except Exception as e:
        logger.error(f"Error getting documents: {str(e)}")
        return []


def find_relevant_docs(query, docs):
    """Simple keyword matching to find relevant documents"""
    # Sanitize query to prevent NoSQL injection
    sanitized_query = sanitize_input(query) if query else ""
    query_words = [sanitize_input(word) for word in sanitized_query.lower().split()]
    relevant = []

    for doc in docs:
        score = 0
        content = doc.get("content_preview", "").lower()
        service_name = doc.get("service_name", "").lower()
        doc_name = doc.get("doc_name", "").lower()

        for word in query_words:
            if word in content:
                score += 2
            if word in service_name:
                score += 3
            if word in doc_name:
                score += 1

        if score > 0:
            doc["relevance_score"] = score
            relevant.append(doc)

    relevant.sort(key=lambda x: x["relevance_score"], reverse=True)
    return relevant[:3]


def load_document_content(relevant_docs):
    """Load document content from S3"""
    s3 = boto3.client("s3")
    bucket = "cloudops-assistant-service-docs"
    context_docs = []

    for doc in relevant_docs:
        try:
            response = s3.get_object(Bucket=bucket, Key=doc["s3_key"])
            content = response["Body"].read().decode("utf-8")
            context_docs.append(
                {
                    "service": doc["service_name"],
                    "document": doc["doc_name"],
                    "content": content[:2000],
                }
            )
        except s3.exceptions.NoSuchKey:
            logger.warning(f"S3 object not found: {doc['s3_key']}")
        except Exception as e:
            logger.error(f"Error reading S3 object {doc['s3_key']}: {str(e)}")

    return context_docs


def call_bedrock_ai(prompt):
    """Call AWS Bedrock for AI response"""
    bedrock = boto3.client("bedrock-runtime")
    response = bedrock.invoke_model(
        modelId="amazon.nova-lite-v1:0",
        body=json.dumps(
            {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 1000, "temperature": 0.7},
            }
        ),
    )
    result = json.loads(response["body"].read().decode("utf-8"))
    return result["output"]["message"]["content"][0]["text"]


def generate_ai_response(query, relevant_docs):
    """Generate AI response using Bedrock"""
    try:
        if not relevant_docs:
            return {
                "answer": "I couldn't find any relevant documentation for your query. Please make sure you've uploaded service documentation first.",
                "sources": [],
            }

        context_docs = load_document_content(relevant_docs)
        if not context_docs:
            return {
                "answer": "No accessible documentation found for your query.",
                "sources": [],
            }

        context = "\n\n".join(
            [
                f"Service: {doc['service']}\nDocument: {doc['document']}\nContent: {doc['content']}"
                for doc in context_docs
            ]
        )

        prompt = (
            f"Based on the following service documentation, answer this question: {query}\n\n"
            f"Documentation:\n{context}\n\n"
            "Please provide a helpful answer with specific steps or information from the documentation. "
            "If the documentation doesn't contain the answer, say so clearly."
        )

        try:
            answer = call_bedrock_ai(prompt)
            return {
                "answer": answer,
                "sources": [
                    {"service": doc["service"], "document": doc["document"]}
                    for doc in context_docs
                ],
            }
        except Exception as bedrock_error:
            logger.error(f"Bedrock API error: {str(bedrock_error)}")
            fallback_answer = "Based on the available documentation: " + (
                context_docs[0]["content"][:500] + "..."
                if context_docs
                else "No relevant documentation found."
            )
            return {
                "answer": fallback_answer,
                "sources": [
                    {"service": doc["service"], "document": doc["document"]}
                    for doc in context_docs
                ],
            }

    except Exception as e:
        logger.error(f"AI response error: {str(e)}")
        return {
            "answer": "I encountered an error while processing your query. Please try again or contact support if the issue persists.",
            "sources": [],
        }


def get_document(event, user_id):
    """Get document content for viewing/editing"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])

        if not all([service_name, doc_name]):
            return error_response(400, "Missing required fields")

        # Additional validation to prevent path traversal
        if (
            ".." in service_name
            or ".." in doc_name
            or "/" in service_name
            or "/" in doc_name
        ):
            return error_response(400, "Invalid service or document name")

        s3 = boto3.client("s3")
        bucket = "cloudops-assistant-service-docs"
        s3_key = f"shared/{service_name}/{doc_name}"

        try:
            response = s3.get_object(Bucket=bucket, Key=s3_key)
            content = response["Body"].read().decode("utf-8")

            return success_response(
                {
                    "service_name": service_name,
                    "doc_name": doc_name,
                    "content": content,
                }
            )
        except s3.exceptions.NoSuchKey:
            return error_response(404, "Document not found")

    except Exception as e:
        logger.error(f"Get document error: {str(e)}")
        return error_response(500, str(e))


def delete_document(event, user_id):
    """Delete a document"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])

        if not all([service_name, doc_name]):
            return error_response(400, "Missing required fields")

        # Additional validation to prevent path traversal and injection
        if (
            ".." in service_name
            or ".." in doc_name
            or "/" in service_name
            or "/" in doc_name
        ):
            return error_response(400, "Invalid service or document name")

        # Delete from S3
        s3 = boto3.client("s3")
        bucket = "cloudops-assistant-service-docs"
        s3_key = f"shared/{service_name}/{doc_name}"

        try:
            s3.delete_object(Bucket=bucket, Key=s3_key)
        except Exception as e:
            logger.warning(f"Failed to delete S3 object {s3_key}: {str(e)}")

        # Delete from DynamoDB
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

        # Use sanitized inputs for delete operation with additional validation
        if not re.match(r"^[a-zA-Z0-9._-]+$", service_name) or not re.match(
            r"^[a-zA-Z0-9._-]+$", doc_name
        ):
            return error_response(400, "Invalid characters in service or document name")

        table.delete_item(
            Key={"service_name": service_name, "doc_name": doc_name},
            ConditionExpression="attribute_exists(service_name) AND attribute_exists(doc_name)",
        )

        return success_response({"message": "Document deleted successfully"})

    except Exception as e:
        logger.error(f"Delete document error: {str(e)}")
        return error_response(500, str(e))
