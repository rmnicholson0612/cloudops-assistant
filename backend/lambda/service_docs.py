import base64
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


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
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
                "body": "",
            }

        # Extract user_id from JWT token
        user_id = extract_user_id(event)
        if not user_id:
            return {
                "statusCode": 401,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Unauthorized"}),
            }

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
            return {
                "statusCode": 200,
                "headers": {
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                },
                "body": "",
            }
        else:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Not found"}),
            }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


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
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Missing required fields"}),
            }

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

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "message": "Service registered successfully",
                    "service_name": service_name,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Register error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def list_available_services(user_id):
    """List services available from GitHub repo scans"""
    try:
        # Get terraform plans to extract repo names
        dynamodb = boto3.resource("dynamodb")
        plans_table = dynamodb.Table("cloudops-assistant-terraform-plans")

        response = plans_table.query(
            IndexName="user-id-index",
            KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(user_id),
        )

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

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"available_services": available_services}),
        }

    except Exception as e:
        logger.error(f"List services error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def handle_upload(event, user_id):
    """Handle document upload"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])
        content = body["content"]  # Don't sanitize content as it's document text

        if not all([service_name, doc_name, content]):
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Missing required fields"}),
            }

        s3 = boto3.client("s3")
        bucket = "cloudops-assistant-service-docs"
        s3_key = f"shared/{service_name}/{doc_name}"

        s3.put_object(
            Bucket=bucket, Key=s3_key, Body=content, ContentType="text/markdown"
        )

        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

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
                "uploaded_by": user_id,
                "ttl": int(
                    (datetime.now(timezone.utc) + timedelta(days=90)).timestamp()
                ),
            }
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "message": "Document uploaded successfully",
                    "service_name": service_name,
                    "doc_name": doc_name,
                }
            ),
        }

    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def handle_search(event, user_id):
    """Handle documentation search with AI"""
    try:
        body = json.loads(event["body"])
        query = body["query"]

        if not query:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Query is required"}),
            }

        docs = get_all_documents()
        relevant_docs = find_relevant_docs(query, docs)
        ai_response = generate_ai_response(query, relevant_docs)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "query": query,
                    "answer": ai_response["answer"],
                    "sources": ai_response["sources"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
        }

    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def list_documents(user_id):
    """List all documents grouped by service"""
    try:
        docs = get_all_documents()

        services = {}
        for doc in docs:
            service_name = doc["service_name"]
            if service_name not in services:
                services[service_name] = []
            services[service_name].append(
                {
                    "doc_name": doc["doc_name"],
                    "upload_date": doc["upload_date"],
                    "file_size": int(doc.get("file_size", 0)),
                }
            )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {"services": services, "total_documents": len(docs)}, default=str
            ),  # Fix Decimal serialization
        }

    except Exception as e:
        logger.error(f"List error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def get_all_documents():
    """Get all documents for all users"""
    try:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table("cloudops-assistant-service-docs-v2")

        response = table.scan()

        return response.get("Items", [])
    except Exception as e:
        logger.error(f"Error getting documents: {str(e)}")
        return []


def find_relevant_docs(query, docs):
    """Simple keyword matching to find relevant documents"""
    query_words = query.lower().split()
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


def generate_ai_response(query, relevant_docs):
    """Generate AI response using Bedrock"""
    try:
        if not relevant_docs:
            return {
                "answer": (
                    "I couldn't find any relevant documentation for your query. "
                    "Please make sure you've uploaded service documentation first."
                ),
                "sources": [],
            }

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
            except Exception as e:
                logger.error(f"Error reading S3 object {doc['s3_key']}: {str(e)}")

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

        return {
            "answer": result["output"]["message"]["content"][0]["text"],
            "sources": [
                {"service": doc["service"], "document": doc["document"]}
                for doc in context_docs
            ],
        }

    except Exception as e:
        logger.error(f"AI response error: {str(e)}")
        return {
            "answer": f"I encountered an error while processing your query: {str(e)}",
            "sources": [],
        }


def get_document(event, user_id):
    """Get document content for viewing/editing"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])

        if not all([service_name, doc_name]):
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Missing required fields"}),
            }

        s3 = boto3.client("s3")
        bucket = "cloudops-assistant-service-docs"
        s3_key = f"shared/{service_name}/{doc_name}"

        try:
            response = s3.get_object(Bucket=bucket, Key=s3_key)
            content = response["Body"].read().decode("utf-8")

            return {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps(
                    {
                        "service_name": service_name,
                        "doc_name": doc_name,
                        "content": content,
                    }
                ),
            }
        except s3.exceptions.NoSuchKey:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Document not found"}),
            }

    except Exception as e:
        logger.error(f"Get document error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }


def delete_document(event, user_id):
    """Delete a document"""
    try:
        body = json.loads(event["body"])
        service_name = sanitize_input(body["service_name"])
        doc_name = sanitize_input(body["doc_name"])

        if not all([service_name, doc_name]):
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Missing required fields"}),
            }

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

        table.delete_item(Key={"service_name": service_name, "doc_name": doc_name})

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"message": "Document deleted successfully"}),
        }

    except Exception as e:
        logger.error(f"Delete document error: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": str(e)}),
        }
