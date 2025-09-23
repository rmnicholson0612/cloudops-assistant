#!/usr/bin/env python3
"""
Local development server for CloudOps Assistant
Runs Lambda functions locally against LocalStack
"""

import os
import sys
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add backend lambda directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend', 'lambda'))

# Set LocalStack environment
os.environ['AWS_ENDPOINT_URL'] = 'http://localhost:4566'
os.environ['AWS_ACCESS_KEY_ID'] = 'test'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test'
os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'

# Set up local AI provider
from ai_providers import get_ai_provider
local_ai = get_ai_provider()

app = Flask(__name__)
CORS(app, origins=['http://localhost:3000'], supports_credentials=True, methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# Initialize LocalStack from SAM template
def init_localstack_from_template():
    import subprocess
    import os
    try:
        script_path = os.path.join(os.path.dirname(__file__), 'deploy-to-localstack.py')
        subprocess.run(['python', script_path], check=True)
    except Exception as e:
        import logging
        logging.error(f"LocalStack initialization failed: {e}")
        print(f"LocalStack initialization failed: {e}")

# Initialize LocalStack on startup
init_localstack_from_template()

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = 'http://localhost:3000'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

# Mock Lambda context
class MockContext:
    def __init__(self):
        self.function_name = 'local-dev'
        self.aws_request_id = 'local-request-id'

# Consistent mock token for local development
LOCAL_DEV_TOKEN = os.environ.get('LOCAL_DEV_TOKEN', 'mock-jwt-token-local-dev-12345')

def validate_local_auth(headers):
    """Validate authorization for local development"""
    auth_header = headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    token = auth_header.replace('Bearer ', '')
    return token == LOCAL_DEV_TOKEN

def create_api_event(method, path, body=None, headers=None):
    """Create API Gateway event structure"""
    event_headers = headers or {}

    # Always set Content-Type for consistency
    if 'Content-Type' not in event_headers:
        event_headers['Content-Type'] = 'application/json'

    # Add mock user info for local development
    event = {
        'httpMethod': method,
        'path': path,
        'pathParameters': {},
        'queryStringParameters': {},
        'headers': event_headers,
        'body': json.dumps(body) if body is not None else None,
        'isBase64Encoded': False,
        'user_info': {
            'user_id': 'local-user',
            'email': 'test@local.dev'
        }
    }

    return event

# Route handlers
@app.route('/auth/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def auth_handler(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    # Mock authentication for local development
    if subpath == 'register':
        return jsonify({
            'message': 'User registered successfully',
            'user': {'id': 'local-user', 'email': 'test@local.dev'}
        })
    elif subpath == 'login':
        return jsonify({
            'access_token': LOCAL_DEV_TOKEN,
            'id_token': LOCAL_DEV_TOKEN,
            'refresh_token': f'{LOCAL_DEV_TOKEN}-refresh',
            'user': {'id': 'local-user', 'email': 'test@local.dev'},
            'message': 'Login successful'
        })
    elif subpath == 'verify':
        return jsonify({
            'valid': True,
            'user': {'id': 'local-user', 'email': 'test@local.dev'}
        })

    return jsonify({'message': f'Mock auth endpoint: {subpath}'}), 200

@app.route('/upload-plan', methods=['POST', 'OPTIONS'])
def upload_plan():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from plan_processor import lambda_handler
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        # Add mock authorization for local development
        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('POST', '/upload-plan', request.get_json(), headers)

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Plan processor error: {e}")
        import html
        safe_error = html.escape(str(e))[:200]
        return jsonify({'error': f'Plan processing failed: {safe_error}'}), 500

@app.route('/costs/<path:subpath>', methods=['GET', 'OPTIONS'])
def costs(subpath):
    # Generate recent dates for trends
    today = datetime.now()
    dates = [(today - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(30, 0, -1)]

    mock_data = {
        'current': {
            'total_cost': 125.43,
            'currency': 'USD',
            'period': 'month-to-date'
        },
        'services': {
            'services': [
                {'service': 'Amazon Elastic Compute Cloud - Compute', 'cost': '45.20'},
                {'service': 'AWS Lambda', 'cost': '12.15'},
                {'service': 'Amazon DynamoDB', 'cost': '8.30'},
                {'service': 'Amazon Simple Storage Service', 'cost': '15.78'},
                {'service': 'Amazon API Gateway', 'cost': '3.45'}
            ]
        },
        'trends': {
            'daily_costs': [{'date': date, 'cost': round(120 + (i * 0.5), 2)} for i, date in enumerate(dates)]
        },
        'by-tag': {
            'services': [
                {'service': 'Environment: Production', 'cost': '75.20'},
                {'service': 'Environment: Development', 'cost': '35.15'},
                {'service': 'Team: Backend', 'cost': '45.30'},
                {'service': 'Team: Frontend', 'cost': '25.73'}
            ]
        },
        'tags': {
            'services': [
                {'service': 'Environment: Production', 'cost': '75.20'},
                {'service': 'Environment: Development', 'cost': '35.15'},
                {'service': 'Team: Backend', 'cost': '45.30'},
                {'service': 'Team: Frontend', 'cost': '25.73'}
            ]
        }
    }
    return jsonify(mock_data.get(subpath, {}))

@app.route('/plan-history/<repo>', methods=['GET', 'OPTIONS'])
def plan_history(repo):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from plan_history import lambda_handler
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('GET', f'/plan-history/{repo}', None, headers)
        event['pathParameters'] = {'repo': repo}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Plan history error: {e}")
        return jsonify({'plans': [], 'repo_name': repo, 'total': 0})

@app.route('/plan-details/<plan_id>', methods=['GET', 'OPTIONS'])
def plan_details(plan_id):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from plan_history import lambda_handler
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('GET', f'/plan-details/{plan_id}', None, headers)
        event['pathParameters'] = {'plan_id': plan_id}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Plan details error: {e}")
        return jsonify({'plan_id': plan_id, 'repo_name': 'test-repo', 'plan_content': 'Mock plan content', 'timestamp': '2024-01-01T00:00:00Z'})

@app.route('/budgets/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def budgets(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    # Handle budget endpoints with hybrid approach: real budgets + mock costs
    if subpath == 'status' and request.method == 'GET':
        return get_budget_status_with_mock_costs()
    elif subpath == 'alerts' and request.method == 'GET':
        return get_budget_alerts_from_db()

    # For configure/delete/update endpoints, use actual Lambda function
    if subpath == 'configure' and request.method == 'POST':
        return handle_budget_configure()
    elif subpath.startswith('delete/') and request.method == 'DELETE':
        return handle_budget_delete(subpath)
    elif subpath.startswith('update/') and request.method == 'PUT':
        return handle_budget_update(subpath)

    return jsonify({'message': f'Budget endpoint: {subpath}'}), 200

@app.route('/drift/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def drift(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    # Use actual Lambda function for all drift endpoints
    try:
        from drift_config import lambda_handler
        os.environ['DRIFT_CONFIG_TABLE'] = 'cloudops-assistant-drift-config'
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        # Only parse JSON for POST/PUT requests
        body = None
        if request.method in ['POST', 'PUT'] and request.content_length:
            body = request.get_json()

        event = create_api_event(request.method, f'/drift/{subpath}', body, headers)

        # Handle path parameters for different endpoints
        if subpath.startswith('delete/'):
            config_id = subpath.replace('delete/', '')
            event['pathParameters'] = {'config_id': config_id}
        elif subpath.startswith('scan/'):
            config_id = subpath.replace('scan/', '')
            event['pathParameters'] = {'config_id': config_id}
        elif subpath.startswith('update/'):
            config_id = subpath.replace('update/', '')
            event['pathParameters'] = {'config_id': config_id}
        elif '/' in subpath:
            parts = subpath.split('/')
            event['pathParameters'] = {'config_id': parts[-1]}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Drift config error: {e}")
        import traceback
        traceback.print_exc()
        import html
        safe_error = html.escape(str(e))[:200]
        return jsonify({'error': f'Drift endpoint failed: {safe_error}'}), 500

@app.route('/scan-repos', methods=['POST', 'OPTIONS'])
def scan_repos():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from repo_scanner import lambda_handler

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('POST', '/scan-repos', request.get_json(), headers)
        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Repo scanner error: {e}")
        return jsonify({
            'error': f'Repo scanner failed: {str(e)}',
            'target': 'error',
            'total_repos': 0,
            'terraform_repos': 0,
            'results': []
        }), 500

# Additional endpoints from SAM template
@app.route('/ai/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def ai_endpoints(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from ai_explainer import lambda_handler
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        # Only parse JSON for POST requests
        body = None
        if request.method == 'POST' and request.content_length:
            body = request.get_json()

        event = create_api_event(request.method, f'/ai/{subpath}', body, headers)
        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"AI handler error: {e}")
        import traceback
        traceback.print_exc()
        import html
        safe_error = html.escape(str(e))[:200]
        return jsonify({'error': f'AI endpoint failed: {safe_error}'}), 500



@app.route('/postmortems', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/postmortems/<path:subpath>', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
def postmortems(subpath=None):
    if request.method == 'OPTIONS':
        return '', 200

    # Handle AI chat for postmortems locally
    if subpath == 'chat' and request.method == 'POST':
        return handle_local_postmortem_chat()

    try:
        from postmortem_generator import lambda_handler
        os.environ['POSTMORTEMS_TABLE'] = 'PostmortemsTable'
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        path = f'/postmortems/{subpath}' if subpath else '/postmortems'
        event = create_api_event(request.method, path, request.get_json(), headers)
        if subpath:
            event['pathParameters'] = {'postmortem_id': subpath}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Postmortem handler error: {e}")
        import html
        safe_subpath = html.escape(str(subpath)) if subpath else 'None'
        return jsonify({'postmortems': [], 'message': f'Postmortem endpoint: {safe_subpath}'})

def handle_local_postmortem_chat():
    """Handle postmortem chat using local AI"""
    try:
        data = request.get_json()
        message = data.get('message', '')
        conversation_history = data.get('conversation_history', [])

        # Build context from conversation
        context = "\n".join([f"{msg['role']}: {msg['content']}" for msg in conversation_history[-5:]])

        prompt = f"""You are helping with an incident postmortem. Ask probing questions to gather details.

Conversation so far:
{context}

User: {message}

Respond with a helpful follow-up question or analysis:"""

        response = local_ai.invoke_model(prompt, max_tokens=300)

        import json
        body = json.loads(response['body'])
        ai_response = body['content'][0]['text']

        return jsonify({
            'response': ai_response,
            'ai_provider': 'ollama',
            'continue_conversation': True
        })

    except Exception as e:
        print(f"Local postmortem chat error: {e}")
        return jsonify({
            'response': 'I\'m having trouble processing that. Can you tell me more about the incident?',
            'ai_provider': 'fallback',
            'continue_conversation': True
        }), 500

@app.route('/discovery/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def discovery(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from resource_discovery import lambda_handler
        os.environ['RESOURCE_DISCOVERY_TABLE'] = 'cloudops-assistant-resource-discovery'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        # Only parse JSON for POST requests
        body = None
        if request.method == 'POST' and request.content_length:
            body = request.get_json()

        event = create_api_event(request.method, f'/discovery/{subpath}', body, headers)

        # Handle path parameters for different endpoints
        if subpath.startswith('status/'):
            scan_id = subpath.replace('status/', '')
            event['pathParameters'] = {'scan_id': scan_id}
        elif subpath.startswith('approve/'):
            service_id = subpath.replace('approve/', '')
            event['pathParameters'] = {'service_id': service_id}
        elif subpath.startswith('reject/'):
            service_id = subpath.replace('reject/', '')
            event['pathParameters'] = {'service_id': service_id}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Discovery handler error: {e}")
        import traceback
        traceback.print_exc()
        import html
        safe_error = html.escape(str(e))[:200]
        return jsonify({'error': f'Discovery endpoint failed: {safe_error}'}), 500

@app.route('/docs/<path:subpath>', methods=['GET', 'POST', 'DELETE', 'OPTIONS'])
def docs(subpath):
    if request.method == 'OPTIONS':
        return '', 200
    import html
    safe_subpath = html.escape(str(subpath))
    return jsonify({'services': [], 'message': f'Docs endpoint: {safe_subpath}'})

@app.route('/slack/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def slack(subpath):
    if request.method == 'OPTIONS':
        return '', 200
    import html
    safe_subpath = html.escape(str(subpath))
    return jsonify({'message': f'Slack endpoint: {safe_subpath}'})

@app.route('/pr-webhook', methods=['POST', 'OPTIONS'])
def pr_webhook():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify({'message': 'PR webhook received'})

@app.route('/pr-reviews', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/pr-reviews/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def pr_reviews(subpath=None):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from pr_reviews_api import lambda_handler
        os.environ['PR_REVIEWS_TABLE'] = 'cloudops-assistant-pr-reviews'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        path = f'/pr-reviews/{subpath}' if subpath else '/pr-reviews'
        event = create_api_event(request.method, path, request.get_json(), headers)
        if subpath:
            event['pathParameters'] = {'review_id': subpath}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"PR reviews handler error: {e}")
        import html
        safe_subpath = html.escape(str(subpath)) if subpath else 'None'
        return jsonify({'reviews': [], 'message': f'PR reviews endpoint: {safe_subpath}'})

@app.route('/users', methods=['GET', 'OPTIONS'])
def users():
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from postmortem_generator import lambda_handler

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('GET', '/users', None, headers)
        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Users handler error: {e}")
        return jsonify({'users': [{'id': 'local-user', 'email': 'test@local.dev'}]})

@app.route('/eol/<path:subpath>', methods=['GET', 'POST', 'DELETE', 'OPTIONS'])
def eol_tracker(subpath):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from eol_tracker import lambda_handler
        os.environ['EOL_DATABASE_TABLE'] = 'cloudops-assistant-eol-database'
        os.environ['EOL_SCANS_TABLE'] = 'cloudops-assistant-eol-scans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        # Only parse JSON for POST requests
        body = None
        if request.method == 'POST' and request.content_length:
            body = request.get_json()

        event = create_api_event(request.method, f'/eol/{subpath}', body, headers)
        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"EOL tracker handler error: {e}")
        import traceback
        traceback.print_exc()
        import html
        safe_error = html.escape(str(e))[:200]
        return jsonify({'error': f'EOL tracker endpoint failed: {safe_error}'}), 500

@app.route('/compare-plans/<plan1>/<plan2>', methods=['GET', 'OPTIONS'])
def compare_plans(plan1, plan2):
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from plan_history import lambda_handler
        os.environ['TERRAFORM_PLANS_TABLE'] = 'cloudops-assistant-terraform-plans'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('GET', f'/compare-plans/{plan1}/{plan2}', None, headers)
        event['pathParameters'] = {'plan1': plan1, 'plan2': plan2}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']
    except Exception as e:
        print(f"Plan comparison error: {e}")
        # Properly escape error message to prevent XSS
        import html
        safe_error = html.escape(str(e))[:200]
        # Also escape plan IDs to prevent XSS through URL parameters
        safe_plan1 = html.escape(str(plan1))[:50]
        safe_plan2 = html.escape(str(plan2))[:50]
        return jsonify({'diff': [f'Comparison failed: {safe_error}'], 'plan1': {'id': safe_plan1, 'timestamp': '2024-01-01'}, 'plan2': {'id': safe_plan2, 'timestamp': '2024-01-02'}}), 500

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'mode': 'local-development',
        'localstack': 'http://localhost:4566',
        'endpoints': ['/auth', '/upload-plan', '/costs', '/plan-history', '/budgets', '/drift', '/ai', '/postmortems', '/discovery', '/docs', '/slack', '/pr-reviews', '/eol']
    })

@app.route('/debug/drift', methods=['GET'])
def debug_drift():
    """Debug endpoint to check drift monitoring setup"""
    try:
        import boto3
        from decimal import Decimal

        # Check DynamoDB connection
        dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:4566', region_name='us-east-1')

        # Check if drift config table exists
        drift_table = dynamodb.Table('cloudops-assistant-drift-config')

        # Try to scan the table
        response = drift_table.scan(Limit=10)

        # Convert Decimal objects to float for JSON serialization
        def convert_decimals(obj):
            if isinstance(obj, list):
                return [convert_decimals(item) for item in obj]
            elif isinstance(obj, dict):
                return {key: convert_decimals(value) for key, value in obj.items()}
            elif isinstance(obj, Decimal):
                return float(obj)
            else:
                return obj

        items = convert_decimals(response.get('Items', []))

        return jsonify({
            'status': 'success',
            'table_exists': True,
            'item_count': response.get('Count', 0),
            'items': items,
            'localstack_endpoint': 'http://localhost:4566',
            'table_name': 'cloudops-assistant-drift-config'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e),
            'localstack_endpoint': 'http://localhost:4566'
        }), 500

def get_budget_status_with_mock_costs():
    """Get real budgets from DB but calculate against mock cost data"""
    try:
        import boto3
        from datetime import datetime

        # Mock current spending data
        mock_current_spending = 67.50

        # Get real budgets from LocalStack DynamoDB
        dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:4566', region_name='us-east-1')
        table = dynamodb.Table('cloudops-assistant-budget-config')

        response = table.scan(
            FilterExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': 'local-user'}
        )

        budgets = []
        for item in response.get('Items', []):
            monthly_limit = float(item['monthly_limit'])
            percentage_used = (mock_current_spending / monthly_limit * 100) if monthly_limit > 0 else 0

            # Check exceeded thresholds
            exceeded_thresholds = []
            for threshold in item.get('thresholds', []):
                if percentage_used >= threshold:
                    exceeded_thresholds.append(threshold)

            import html
            # Sanitize all user-controlled fields to prevent XSS
            safe_budget_id = html.escape(str(item.get('budget_id', '')))[:50]
            safe_budget_name = html.escape(str(item.get('budget_name', '')))[:100]
            safe_service_filter = html.escape(str(item.get('service_filter', 'all')))[:50]

            budgets.append({
                'budget_id': safe_budget_id,
                'budget_name': safe_budget_name,
                'monthly_limit': monthly_limit,
                'current_spending': mock_current_spending,
                'percentage_used': round(percentage_used, 1),
                'projected_monthly': 85.0,  # Mock projection
                'days_remaining': 12,
                'burn_rate_daily': 2.25,
                'exceeded_thresholds': exceeded_thresholds,
                'service_filter': safe_service_filter,
                'status': 'over_budget' if percentage_used > 100 else 'warning' if exceeded_thresholds else 'on_track'
            })

        return jsonify({
            'budgets': budgets,
            'last_updated': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"Budget status error: {e}")
        return jsonify({'budgets': [], 'last_updated': datetime.now().isoformat()})

def get_budget_alerts_from_db():
    """Get budget alerts from real budget configurations"""
    try:
        import boto3

        dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:4566', region_name='us-east-1')
        table = dynamodb.Table('cloudops-assistant-budget-config')

        response = table.scan(
            FilterExpression='user_id = :uid',
            ExpressionAttributeValues={':uid': 'local-user'}
        )

        alerts = []
        for item in response.get('Items', []):
            # Simulate alerts for budgets that would exceed thresholds with mock data
            mock_percentage = 67.5  # Mock current usage
            for threshold in item.get('thresholds', []):
                if mock_percentage >= threshold:
                    alerts.append({
                        'budget_name': item['budget_name'],
                        'threshold': threshold,
                        'alert_time': '2024-01-15T08:00:00Z',  # Mock alert time
                        'budget_id': item['budget_id']
                    })

        return jsonify({
            'alerts': alerts,
            'total_alerts': len(alerts)
        })

    except Exception as e:
        print(f"Budget alerts error: {e}")
        return jsonify({'alerts': [], 'total_alerts': 0})

def handle_budget_configure():
    """Handle budget configuration using actual Lambda function"""
    try:
        from budget_manager import lambda_handler

        os.environ['BUDGET_CONFIG_TABLE'] = 'cloudops-assistant-budget-config'
        os.environ['COST_CACHE_TABLE'] = 'cloudops-assistant-cost-cache'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        event = create_api_event('POST', '/budgets/configure', request.get_json(), headers)

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']

    except Exception as e:
        print(f"Budget configure error: {e}")
        return jsonify({'error': f'Budget configuration failed: {str(e)}'}), 500

def handle_budget_delete(subpath):
    """Handle budget deletion using actual Lambda function"""
    try:
        from budget_manager import lambda_handler

        os.environ['BUDGET_CONFIG_TABLE'] = 'cloudops-assistant-budget-config'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        budget_id = subpath.replace('delete/', '')
        event = create_api_event('DELETE', f'/budgets/{subpath}', None, headers)
        event['pathParameters'] = {'budget_id': budget_id}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']

    except Exception as e:
        print(f"Budget delete error: {e}")
        return jsonify({'error': f'Budget deletion failed: {str(e)}'}), 500

def handle_budget_update(subpath):
    """Handle budget update using actual Lambda function"""
    try:
        from budget_manager import lambda_handler

        os.environ['BUDGET_CONFIG_TABLE'] = 'cloudops-assistant-budget-config'
        os.environ['COST_CACHE_TABLE'] = 'cloudops-assistant-cost-cache'

        headers = dict(request.headers)
        if not validate_local_auth(headers):
            headers['Authorization'] = f'Bearer {LOCAL_DEV_TOKEN}'

        budget_id = subpath.replace('update/', '')
        event = create_api_event('PUT', f'/budgets/{subpath}', request.get_json(), headers)
        event['pathParameters'] = {'budget_id': budget_id}

        result = lambda_handler(event, MockContext())
        return jsonify(json.loads(result['body'])), result['statusCode']

    except Exception as e:
        print(f"Budget update error: {e}")
        return jsonify({'error': f'Budget update failed: {str(e)}'}), 500

if __name__ == '__main__':
    print("CloudOps Assistant Local Server")
    print("API: http://localhost:8080")
    print("LocalStack: http://localhost:4566")
    app.run(host='0.0.0.0', port=8080, debug=True)
