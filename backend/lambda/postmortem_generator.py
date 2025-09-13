import json
import logging
import os
import uuid
from datetime import datetime, timedelta

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
postmortems_table = dynamodb.Table("PostmortemsTable")
plans_table = dynamodb.Table("TerraformPlansTable")
bedrock = boto3.client("bedrock-runtime")
cognito = boto3.client("cognito-idp")
cost_explorer = boto3.client("ce")


def lambda_handler(event, context):
    if event.get("httpMethod") == "OPTIONS":
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "content-type,authorization",
                "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            },
            "body": "",
        }

    try:
        path = event.get("path", "")
        method = event.get("httpMethod", "")

        if path == "/postmortems" and method == "GET":
            return get_postmortems(event)
        elif path == "/postmortems" and method == "POST":
            return create_postmortem(event)
        elif path.startswith("/postmortems/") and method == "GET":
            postmortem_id = path.split("/")[-1]
            return get_postmortem(postmortem_id, event)
        elif path.startswith("/postmortems/") and method == "PUT":
            postmortem_id = path.split("/")[-1]
            return update_postmortem(postmortem_id, event)
        elif path.startswith("/postmortems/") and method == "DELETE":
            postmortem_id = path.split("/")[-1]
            return delete_postmortem(postmortem_id, event)
        elif path == "/users" and method == "GET":
            return get_users(event)
        elif path == "/postmortems/suggest" and method == "POST":
            return get_ai_suggestions(event)
        elif path == "/postmortems/previous" and method == "POST":
            return get_previous_postmortems(event)
        elif path == "/postmortems/conversation" and method == "POST":
            return handle_conversation(event)
        elif path == "/postmortems/generate" and method == "POST":
            return generate_final_postmortem(event)
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


def create_postmortem(event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        body_str = event.get("body", "{}")
        if not body_str:
            body_str = "{}"

        logger.info(f"Create postmortem body: {body_str}")
        body = json.loads(body_str)
    except json.JSONDecodeError as e:
        logger.error(
            f"JSON decode error in create postmortem: {str(e)}, "
            f"body: {event.get('body', 'None')}"
        )
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Invalid JSON input"}),
        }

    # Required fields - sanitize inputs
    title = sanitize_input(body.get("title", ""))
    service = sanitize_input(body.get("service", ""))
    severity = sanitize_input(body.get("severity", "medium"))
    start_time = sanitize_input(body.get("start_time", ""))
    end_time = sanitize_input(body.get("end_time", ""))

    # Optional fields
    include_terraform = bool(body.get("include_terraform", False))
    include_costs = bool(body.get("include_costs", False))
    owner_id = sanitize_input(body.get("owner_id", ""))
    incident_summary = sanitize_input(body.get("incident_summary", ""))

    # Validate severity
    if severity not in ["low", "medium", "high"]:
        severity = "medium"

    if not all([title, service, start_time]):
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {"error": "title, service, and start_time are required"}
            ),
        }

    try:
        postmortem_id = str(uuid.uuid4())

        # Gather data based on selections
        terraform_data = []
        cost_data = {}

        if include_terraform:
            terraform_data = get_terraform_plans_in_range(user_id, start_time, end_time)

        if include_costs:
            cost_data = get_cost_data_in_range(start_time, end_time, service)

        # Generate AI analysis if data is available
        ai_analysis = generate_ai_analysis(
            {
                "title": title,
                "service": service,
                "severity": severity,
                "incident_summary": incident_summary,
                "terraform_data": terraform_data,
                "cost_data": cost_data,
                "start_time": start_time,
                "end_time": end_time,
            }
        )

        postmortem_item = {
            "user_id": user_id,
            "postmortem_id": postmortem_id,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "title": title,
            "service": service,
            "severity": severity,
            "status": "draft",
            "start_time": start_time,
            "end_time": end_time,
            "owner_id": owner_id or user_id,
            "incident_summary": incident_summary,
            "include_terraform": include_terraform,
            "include_costs": include_costs,
            "terraform_data": terraform_data,
            "cost_data": cost_data,
            "executive_summary": ai_analysis.get("executive_summary", ""),
            "detailed_timeline": ai_analysis.get("detailed_timeline", []),
            "root_cause_analysis": ai_analysis.get("root_cause_analysis", ""),
            "impact_assessment": ai_analysis.get("impact_assessment", ""),
            "detection_and_response": ai_analysis.get("detection_and_response", ""),
            "resolution_details": ai_analysis.get("resolution_details", ""),
            "lessons_learned": ai_analysis.get("lessons_learned", []),
            "action_items": ai_analysis.get("action_items", []),
            "preventive_measures": ai_analysis.get("preventive_measures", []),
            "monitoring_improvements": ai_analysis.get("monitoring_improvements", []),
            "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
        }

        postmortems_table.put_item(Item=postmortem_item)

        return {
            "statusCode": 201,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "postmortem_id": postmortem_id,
                    "message": "Postmortem created successfully",
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error creating postmortem: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Failed to create postmortem"}),
        }


def get_postmortems(event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        response = postmortems_table.scan(
            FilterExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": user_id},
        )

        postmortems = []
        for item in response["Items"]:
            postmortems.append(
                {
                    "postmortem_id": item["postmortem_id"],
                    "title": item.get("title", "Untitled"),
                    "service": item.get("service", "Unknown"),
                    "severity": item.get("severity", "medium"),
                    "status": item.get("status", "draft"),
                    "owner_id": item.get("owner_id", ""),
                    "created_at": item["created_at"],
                    "updated_at": item.get("updated_at", item["created_at"]),
                    "start_time": item.get("start_time", ""),
                    "end_time": item.get("end_time", ""),
                }
            )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"postmortems": postmortems}),
        }

    except Exception as e:
        logger.error(f"Error getting postmortems: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Failed to get postmortems"}),
        }


def get_postmortem(postmortem_id, event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        response = postmortems_table.scan(
            FilterExpression="postmortem_id = :postmortem_id AND user_id = :user_id",
            ExpressionAttributeValues={
                ":postmortem_id": postmortem_id,
                ":user_id": user_id,
            },
        )

        if not response["Items"]:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Postmortem not found"}),
            }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(response["Items"][0], default=str),
        }

    except Exception as e:
        logger.error(f"Error getting postmortem: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Failed to get postmortem"}),
        }


def update_postmortem(postmortem_id, event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        body = json.loads(event.get("body", "{}"))

        # Get existing postmortem
        response = postmortems_table.scan(
            FilterExpression="postmortem_id = :postmortem_id AND user_id = :user_id",
            ExpressionAttributeValues={
                ":postmortem_id": postmortem_id,
                ":user_id": user_id,
            },
        )

        if not response["Items"]:
            return {
                "statusCode": 404,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Postmortem not found"}),
            }

        # Update fields
        update_expression = "SET updated_at = :updated_at"
        expression_values = {":updated_at": datetime.utcnow().isoformat()}

        updatable_fields = [
            "title",
            "service",
            "severity",
            "status",
            "owner_id",
            "incident_summary",
            "executive_summary",
            "root_cause_analysis",
            "impact_assessment",
            "detection_and_response",
            "resolution_details",
        ]

        for field in updatable_fields:
            if field in body and body[field]:
                update_expression += f", {field} = :{field}"
                expression_values[f":{field}"] = sanitize_input(body[field])

        postmortems_table.update_item(
            Key={"user_id": user_id, "postmortem_id": postmortem_id},
            UpdateExpression=update_expression,
            ExpressionAttributeValues=expression_values,
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"message": "Postmortem updated successfully"}),
        }

    except Exception as e:
        logger.error(f"Error updating postmortem: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to update postmortem: {str(e)}"}),
        }


def delete_postmortem(postmortem_id, event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        postmortems_table.delete_item(
            Key={"user_id": user_id, "postmortem_id": postmortem_id}
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"message": "Postmortem deleted successfully"}),
        }

    except Exception as e:
        logger.error(f"Error deleting postmortem: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Failed to delete postmortem"}),
        }


def get_users(event):
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        # Get user pool ID from environment
        user_pool_id = os.environ.get("USER_POOL_ID")
        if not user_pool_id:
            return {
                "statusCode": 500,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "USER_POOL_ID not configured"}),
            }

        response = cognito.list_users(UserPoolId=user_pool_id)

        users = []
        for user in response["Users"]:
            username = user["Username"]
            email = ""
            for attr in user.get("Attributes", []):
                if attr["Name"] == "email":
                    email = attr["Value"]
                    break

            users.append({"user_id": username, "email": email})

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"users": users}),
        }

    except Exception as e:
        logger.error(f"Error getting users: {str(e)}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"users": []}),  # Return empty list on error
        }


def get_terraform_plans_in_range(user_id, start_time, end_time):
    """Get terraform plans within time range"""
    try:
        response = plans_table.query(
            KeyConditionExpression="user_id = :user_id",
            FilterExpression="created_at BETWEEN :start_time AND :end_time",
            ExpressionAttributeValues={
                ":user_id": user_id,
                ":start_time": start_time,
                ":end_time": end_time,
            },
        )
        return response["Items"]
    except Exception as e:
        logger.error(f"Error getting terraform plans: {str(e)}")
        return []


def get_cost_data_in_range(start_time, end_time, service):
    """Get cost data within time range for specific service"""
    try:
        response = cost_explorer.get_cost_and_usage(
            TimePeriod={"Start": start_time[:10], "End": end_time[:10]},
            Granularity="DAILY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )

        cost_data = {"total_cost": 0, "daily_costs": []}
        for result in response["ResultsByTime"]:
            for group in result["Groups"]:
                if service.lower() in group["Keys"][0].lower():
                    cost = float(group["Metrics"]["BlendedCost"]["Amount"])
                    cost_data["total_cost"] += cost
                    cost_data["daily_costs"].append(
                        {"date": result["TimePeriod"]["Start"], "cost": cost}
                    )

        return cost_data
    except Exception as e:
        logger.error(f"Error getting cost data: {str(e)}")
        return {}


def generate_ai_analysis(data):
    """Generate comprehensive AI analysis for postmortem report"""
    logger.info(f"Starting AI analysis for: {data['title']}")
    try:
        # Build detailed context for AI
        terraform_context = ""
        if data["terraform_data"]:
            terraform_context = "\nTerraform Plans Analysis:\n"
            for i, plan in enumerate(data["terraform_data"][:3]):  # Limit to 3 plans
                repo_name = plan.get("repo_name", "Unknown")
                changes = plan.get("changes_detected", 0)
                terraform_context += f"Plan {i + 1}: {repo_name} - {changes} changes\n"

        cost_context = ""
        if data["cost_data"]:
            cost_context = "\nCost Impact Analysis:\n"
            total_cost = data["cost_data"].get("total_cost", 0)
            cost_context += f"Total Cost: ${total_cost:.2f}\n"
            if "daily_costs" in data["cost_data"]:
                daily_count = len(data["cost_data"]["daily_costs"])
                cost_context += f"Daily Breakdown: {daily_count} days of data\n"

        prompt = f"""
Generate a comprehensive 2-page incident postmortem report for this critical \
infrastructure incident. This should be executive-level quality suitable for \
stakeholders and engineering teams.

=== INCIDENT DETAILS ===
Title: {data['title']}
Service/Component: {data['service']}
Severity: {data['severity'].upper()}
Incident Window: {data['start_time']} to {data.get('end_time', 'Ongoing')}
Initial Summary: {data['incident_summary']}
{terraform_context}
{cost_context}

=== REQUIREMENTS ===
Create a detailed JSON response with these comprehensive sections:

1. executive_summary: 3-4 paragraph executive summary covering what happened, business impact, and key learnings
2. detailed_timeline: Comprehensive timeline with specific timestamps, technical details, and decision points
3. root_cause_analysis: Deep technical analysis including:
   - Primary root cause
   - Contributing factors
   - System vulnerabilities exposed
   - Process gaps identified
4. impact_assessment: Detailed impact analysis including:
   - Technical impact (systems affected, data integrity, performance)
   - Business impact (revenue, customers, SLA breaches)
   - Operational impact (team resources, escalations)
5. detection_and_response: Detailed narrative covering:
   - How the incident was first detected
   - Alert mechanisms that worked/failed
   - Response timeline and decision making
   - Communication flow
6. resolution_details: Step-by-step resolution process including:
   - Immediate mitigation steps
   - Permanent fix implementation
   - Verification and testing
   - Recovery procedures
7. lessons_learned: Strategic insights including:
   - What worked well
   - What could be improved
   - System design insights
   - Process improvements needed
8. action_items: Prioritized action items with:
   - Immediate actions (0-7 days)
   - Short-term improvements (1-4 weeks)
   - Long-term strategic changes (1-3 months)
9. preventive_measures: Specific technical and process changes to prevent recurrence
10. monitoring_improvements: Enhanced monitoring, alerting, and observability recommendations

Make this report thorough, technical where appropriate, but accessible to both \
engineering and business stakeholders. Include specific recommendations and \
measurable outcomes.
"""

        logger.info("Calling Bedrock for AI analysis")
        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 4000,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )
        logger.info("Bedrock response received")

        response_body = json.loads(response["body"].read())
        ai_content = response_body["content"][0]["text"]

        logger.info(f"AI response content: {ai_content[:200]}...")
        json_start = ai_content.find("{")
        json_end = ai_content.rfind("}") + 1
        if json_start != -1 and json_end != -1:
            parsed_result = json.loads(ai_content[json_start:json_end])
            logger.info("Successfully parsed AI response")
            return parsed_result
        else:
            logger.warning("No JSON found in AI response")

    except Exception as e:
        logger.error(f"AI analysis failed: {str(e)}", exc_info=True)

    return {
        "executive_summary": "Comprehensive analysis pending - manual review required",
        "detailed_timeline": [],
        "root_cause_analysis": "Deep root cause analysis to be completed",
        "impact_assessment": "Full impact assessment pending",
        "detection_and_response": "Detection and response analysis to be added",
        "resolution_details": "Resolution process documentation pending",
        "lessons_learned": ["Comprehensive lessons learned analysis needed"],
        "action_items": ["Complete detailed incident analysis"],
        "preventive_measures": ["Implement preventive measures based on analysis"],
        "monitoring_improvements": ["Enhance monitoring based on incident learnings"],
    }


def get_ai_suggestions(event):
    """Get AI suggestions for postmortem fields"""
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    body = json.loads(event.get("body", "{}"))
    field = body.get("field")
    context = body.get("context", {})

    try:
        prompt = f"""
Provide AI suggestions for the '{field}' field in an incident postmortem.

Context:
- Title: {context.get('title', 'Not provided')}
- Service: {context.get('service', 'Not provided')}
- Severity: {context.get('severity', 'Not provided')}
- Summary: {context.get('summary', 'Not provided')}

Provide 3-5 specific, actionable suggestions for the '{field}' field. Return as JSON array of strings.
"""

        response = bedrock.invoke_model(
            modelId="anthropic.claude-3-sonnet-20240229-v1:0",
            body=json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )

        response_body = json.loads(response["body"].read())
        ai_content = response_body["content"][0]["text"]

        # Extract JSON array from response
        json_start = ai_content.find("[")
        json_end = ai_content.rfind("]") + 1
        if json_start != -1 and json_end != -1:
            suggestions = json.loads(ai_content[json_start:json_end])
        else:
            suggestions = ["AI suggestion generation failed"]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"suggestions": suggestions}),
        }

    except Exception as e:
        logger.error(f"Error getting AI suggestions: {str(e)}")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"suggestions": ["Manual input required"]}),
        }


def get_previous_postmortems(event):
    """Get previous postmortems for a service"""
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    body = json.loads(event.get("body", "{}"))
    service = sanitize_input(body.get("service", ""))

    if not service:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Service parameter required"}),
        }

    try:
        from boto3.dynamodb.conditions import Attr

        response = postmortems_table.scan(
            FilterExpression=Attr("user_id").eq(user_id)
            & Attr("service").contains(service)
        )

        postmortems = []
        for pm in response.get("Items", [])[:5]:
            summary = pm.get("executive_summary", "")
            if len(summary) > 200:
                summary = summary[:200] + "..."
            postmortems.append(
                {
                    "id": pm["postmortem_id"],
                    "title": pm.get("title", "Untitled"),
                    "created_at": pm.get("created_at"),
                    "summary": summary,
                }
            )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"previous_postmortems": postmortems}),
        }
    except Exception as e:
        logger.error(f"Error getting previous postmortems: {str(e)}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Failed to get previous postmortems"}),
        }


def sanitize_input(text):
    """Sanitize user input to prevent injection attacks"""
    if not text or not isinstance(text, str):
        return ""
    # Remove potential injection patterns
    sanitized = (
        text.replace('"', "").replace("'", "").replace("\n", " ").replace("\r", " ")
    )
    return sanitized[:500]  # Limit length


def handle_conversation(event):
    """Handle conversational Q&A for postmortem creation"""
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        body_str = event.get("body", "{}")
        if not body_str:
            body_str = "{}"

        body = json.loads(body_str)
        conversation_id = body.get("conversation_id", str(uuid.uuid4()))
        message = sanitize_input(body.get("message", ""))
        context = body.get("context", {})

        if not message:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                },
                "body": json.dumps({"error": "Message is required"}),
            }

        safe_context = {
            "title": sanitize_input(context.get("title", "Not set")),
            "service": sanitize_input(context.get("service", "Not set")),
            "owner": sanitize_input(context.get("owner", "Not set")),
            "description": sanitize_input(context.get("description", "Not set")),
            "timeline": sanitize_input(context.get("timeline", "Not set")),
        }

        # Check if we have enough information
        conversation_history = body.get("conversation_history", [])
        user_responses = [
            msg.get("content", "")
            for msg in conversation_history
            if msg.get("role") == "user"
        ]

        # Simple check for sufficient information
        has_timeline = any(
            "date" in resp.lower() or "time" in resp.lower() or "2025" in resp
            for resp in user_responses
        )
        has_impact = any(
            "impact" in resp.lower()
            or "affect" in resp.lower()
            or "broken" in resp.lower()
            for resp in user_responses
        )
        has_cause = any(
            "cause" in resp.lower() or "error" in resp.lower() or "fail" in resp.lower()
            for resp in user_responses
        )

        if len(user_responses) >= 3 and has_timeline and has_impact and has_cause:
            ai_response = "READY_TO_GENERATE"
        else:
            try:
                prev_responses = "; ".join(user_responses[-2:])
                prompt = (
                    "Based on this conversation about a postmortem, "
                    "what ONE specific question should I ask next?\n\n"
                    f"Context: {safe_context['title']} - {safe_context['service']}\n"
                    f"User just said: {message}\n"
                    f"Previous responses: {prev_responses}\n\n"
                    "Ask ONE specific question about missing details. Be conversational."
                )

                response = bedrock.invoke_model(
                    modelId="amazon.nova-lite-v1:0",
                    body=json.dumps(
                        {
                            "messages": [
                                {"role": "user", "content": [{"text": prompt}]}
                            ],
                            "inferenceConfig": {"maxTokens": 150},
                        }
                    ),
                )

                result = json.loads(response["body"].read())
                ai_response = result["output"]["message"]["content"][0]["text"]
            except Exception as ai_error:
                logger.error(f"AI model error: {str(ai_error)}")
                # Fallback questions when AI is unavailable
                fallback_questions = [
                    "What time did the incident start and when was it resolved?",
                    "What was the impact on users or systems?",
                    "What was the root cause of the issue?",
                    "How was the incident detected?",
                    "What steps were taken to resolve it?",
                ]
                question_index = len(user_responses) % len(fallback_questions)
                ai_response = fallback_questions[question_index]

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {
                    "conversation_id": conversation_id,
                    "response": ai_response,
                    "ready_to_generate": ai_response.strip() == "READY_TO_GENERATE",
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error handling conversation: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to process conversation: {str(e)}"}),
        }


def generate_final_postmortem(event):
    """Generate final postmortem from conversation"""
    user_id = get_user_id_from_token(event)
    if not user_id:
        return {
            "statusCode": 401,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": "Unauthorized"}),
        }

    try:
        body = json.loads(event.get("body", "{}"))
        context = body.get("context", {})
        conversation_summary = sanitize_input(body.get("conversation_summary", ""))

        safe_context = {
            "title": sanitize_input(context.get("title", "")),
            "service": sanitize_input(context.get("service", "")),
            "owner": sanitize_input(context.get("owner", "")),
            "timeline": sanitize_input(context.get("timeline", "")),
            "description": sanitize_input(context.get("description", "")),
        }

        # Try AI generation first, fallback to manual if it fails
        postmortem_data = None
        try:
            prompt = (
                "Create a comprehensive incident postmortem report "
                "based on this conversation.\n\n"
                "=== INCIDENT DETAILS ===\n"
                f"Title: {safe_context['title']}\n"
                f"Service: {safe_context['service']}\n"
                f"Owner: {safe_context['owner']}\n"
                f"Initial Timeline: {safe_context['timeline']}\n"
                f"Description: {safe_context['description']}\n"
                "=== CONVERSATION SUMMARY ===\n"
                f"{conversation_summary}\n"
                "=== REQUIREMENTS ===\n"
                "Generate a detailed JSON response with these sections:\n\n"
                '{"executive_summary": "3-4 paragraph executive summary covering '
                'what happened, business impact, and resolution",\n'
                '  "root_cause_analysis": "Detailed technical analysis of the root '
                'cause based on the conversation",\n'
                '  "impact_assessment": "Comprehensive impact analysis including '
                'technical and business effects",\n'
                '  "detection_and_response": "How the incident was detected and '
                'the response timeline",\n'
                '  "resolution_details": "Step-by-step resolution process and '
                'fix implementation",\n'
                '  "lessons_learned": ["List of key lessons learned from this '
                'incident"],\n'
                '  "action_items": ["Specific action items to prevent recurrence"],\n'
                '  "preventive_measures": ["Technical and process changes to '
                'prevent similar incidents"],\n'
                '  "monitoring_improvements": ["Enhanced monitoring and alerting '
                'recommendations"]\n'
                "}\n\n"
                "Make each section detailed and specific based on the conversation. "
                "Use the actual details discussed, not generic placeholders."
            )

            logger.info("Calling Bedrock for final postmortem generation")
            response = bedrock.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps(
                    {
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 3000,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                ),
            )
            logger.info("Bedrock response received for postmortem generation")

            response_body = json.loads(response["body"].read())
            postmortem_content = response_body["content"][0]["text"]

            logger.info(f"AI postmortem response: {postmortem_content[:500]}...")

            # Try to extract JSON from the response
            json_start = postmortem_content.find("{")
            json_end = postmortem_content.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_content = postmortem_content[json_start:json_end]
                logger.info(f"Extracted JSON: {json_content[:200]}...")
                postmortem_data = json.loads(json_content)
                logger.info("Successfully parsed AI JSON response")
            else:
                raise ValueError("No JSON found in AI response")

        except Exception as ai_error:
            logger.error(f"AI generation failed: {str(ai_error)}")
            postmortem_data = None

        # Fallback to structured data if AI fails
        if not postmortem_data:
            logger.info("Using fallback postmortem generation")
            postmortem_data = {
                "executive_summary": (
                    f"Incident Report: {safe_context['title']} affected "
                    f"{safe_context['service']} operations. Based on the conversation, "
                    "the team identified the issue and implemented a resolution. "
                    "This postmortem documents the incident details and lessons learned."
                ),
                "root_cause_analysis": (
                    "Root cause analysis from conversation: "
                    + (
                        conversation_summary[:300]
                        if conversation_summary
                        else "Analysis based on team discussion and investigation."
                    )
                ),
                "impact_assessment": (
                    f"Impact assessment: The incident affected {safe_context['service']} "
                    "operations and required immediate attention from the team. "
                    "Users may have experienced service disruption."
                ),
                "detection_and_response": (
                    "The incident was detected through monitoring alerts and the team "
                    "responded according to established procedures. Response time and "
                    "escalation followed standard incident management protocols."
                ),
                "resolution_details": (
                    "The team implemented a fix based on the root cause analysis and "
                    "verified the resolution. Post-resolution monitoring confirmed system stability."
                ),
                "lessons_learned": [
                    "Improve monitoring and alerting capabilities",
                    "Enhance incident response procedures",
                    "Document troubleshooting steps for future reference",
                ],
                "action_items": [
                    "Review and update monitoring thresholds",
                    "Conduct post-incident review with stakeholders",
                    "Update runbooks and documentation",
                ],
                "preventive_measures": [
                    "Implement additional monitoring for early detection",
                    "Improve error handling and resilience",
                    "Enhance testing procedures",
                ],
                "monitoring_improvements": [
                    "Add proactive alerts for similar conditions",
                    "Improve dashboard visibility",
                    "Enhance logging and observability",
                ],
            }

        postmortem_id = str(uuid.uuid4())
        current_time = datetime.utcnow().isoformat()

        postmortem = {
            "user_id": user_id,
            "postmortem_id": postmortem_id,
            "title": safe_context["title"] or "Conversational Postmortem",
            "service": safe_context["service"] or "API Gateway",
            "severity": "medium",
            "owner_id": safe_context["owner"] or user_id,
            "status": "completed",
            "created_at": current_time,
            "updated_at": current_time,
            "start_time": current_time,
            "end_time": current_time,
            "incident_summary": (
                safe_context["description"] or "Generated from conversation"
            ),
            "executive_summary": postmortem_data.get(
                "executive_summary", "Executive summary generated from conversation"
            ),
            "detailed_timeline": safe_context["timeline"]
            or "Timeline constructed from conversation",
            "root_cause_analysis": postmortem_data.get(
                "root_cause_analysis", "Root cause analysis from conversation"
            ),
            "impact_assessment": postmortem_data.get(
                "impact_assessment", "Impact assessment from conversation"
            ),
            "detection_and_response": postmortem_data.get(
                "detection_and_response",
                "Detection and response analysis from conversation",
            ),
            "resolution_details": postmortem_data.get(
                "resolution_details", "Resolution details from conversation"
            ),
            "lessons_learned": postmortem_data.get(
                "lessons_learned", ["Lessons learned from conversation"]
            ),
            "action_items": postmortem_data.get(
                "action_items", ["Action items identified in conversation"]
            ),
            "preventive_measures": postmortem_data.get(
                "preventive_measures", ["Preventive measures from conversation"]
            ),
            "monitoring_improvements": postmortem_data.get(
                "monitoring_improvements", ["Monitoring improvements from conversation"]
            ),
            "ttl": int((datetime.utcnow() + timedelta(days=90)).timestamp()),
        }

        postmortems_table.put_item(Item=postmortem)

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(
                {"postmortem_id": postmortem_id, "postmortem": postmortem}
            ),
        }
    except Exception as e:
        logger.error(f"Error generating final postmortem: {str(e)}", exc_info=True)
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps({"error": f"Failed to generate postmortem: {str(e)}"}),
        }


def get_user_id_from_token(event):
    """Extract user ID from JWT token"""
    try:
        auth_header = event.get("headers", {}).get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        # In a real implementation, you'd verify the JWT token
        # For now, we'll extract the user ID from the token payload
        import base64

        payload = token.split(".")[1]
        # Add padding if needed
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))

        return decoded.get("sub")  # 'sub' is the user ID in Cognito tokens

    except Exception as e:
        logger.error(f"Error extracting user ID: {str(e)}")
        return None
