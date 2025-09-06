import json
import boto3
import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
import os

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
ce_client = boto3.client('ce')
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('cost-cache')

def lambda_handler(event, context):
    """
    AWS Cost Explorer integration for CloudOps Assistant
    Endpoints: /costs/current, /costs/services, /costs/trends
    """
    try:
        path = event.get('path', '')
        method = event.get('httpMethod', '')
        
        # Handle CORS preflight
        if method == 'OPTIONS':
            return cors_response()
        
        # Get query parameters
        query_params = event.get('queryStringParameters') or {}
        month = query_params.get('month')  # Format: YYYY-MM
        
        # Validate month parameter if provided
        if month and not re.match(r'^\d{4}-\d{2}$', month):
            return error_response(400, 'Invalid month format. Expected YYYY-MM')
        
        # Route to appropriate handler
        if path == '/costs/current':
            return get_current_costs(month)
        elif path == '/costs/services':
            return get_service_costs(month)
        elif path == '/costs/trends':
            return get_cost_trends()
        elif path == '/costs/by-tag':
            return get_costs_by_tag(month)
        else:
            return error_response(404, 'Endpoint not found')
            
    except Exception as e:
        logger.error(f"Cost analyzer error: {str(e)}")
        return error_response(500, 'Internal server error')

def get_current_costs(month=None):
    """Get month total costs"""
    try:
        # Parse month parameter or use current month
        if month:
            # Validate month format
            if not re.match(r'^\d{4}-\d{2}$', month):
                raise ValueError("Invalid month format. Expected YYYY-MM")
            year, month_num = month.split('-')
            target_date = datetime(int(year), int(month_num), 1)
            cache_key = f"current_costs_{month}_{datetime.now().strftime('%H')}"
        else:
            target_date = datetime.now()
            cache_key = f"current_costs_{datetime.now().strftime('%Y-%m-%d-%H')}"
        
        # Check cache first
        cached = get_from_cache(cache_key)
        if cached:
            return success_response(cached)
        
        # Get month dates
        start_date = target_date.replace(day=1).strftime('%Y-%m-%d')
        # Get last day of month
        if target_date.month == 12:
            next_month = target_date.replace(year=target_date.year + 1, month=1, day=1)
        else:
            next_month = target_date.replace(month=target_date.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Query Cost Explorer
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost']
        )
        
        # Extract total cost
        total_cost = 0
        if response['ResultsByTime']:
            total_cost = float(response['ResultsByTime'][0]['Total']['BlendedCost']['Amount'])
        
        result = {
            'total_cost': round(total_cost, 2),
            'currency': 'USD',
            'period': f"{start_date} to {end_date}",
            'last_updated': datetime.now().isoformat()
        }
        
        # Cache for 1 hour
        cache_result(cache_key, result, 3600)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Error getting current costs: {str(e)}")
        return error_response(500, 'Failed to retrieve current costs')

def get_service_costs(month=None):
    """Get costs broken down by AWS service"""
    try:
        # Parse month parameter or use current month
        if month:
            # Validate month format
            if not re.match(r'^\d{4}-\d{2}$', month):
                raise ValueError("Invalid month format. Expected YYYY-MM")
            year, month_num = month.split('-')
            target_date = datetime(int(year), int(month_num), 1)
            cache_key = f"service_costs_{month}_{datetime.now().strftime('%H')}"
        else:
            target_date = datetime.now()
            cache_key = f"service_costs_{datetime.now().strftime('%Y-%m-%d-%H')}"
        
        # Check cache first
        cached = get_from_cache(cache_key)
        if cached:
            return success_response(cached)
        
        # Get month dates
        start_date = target_date.replace(day=1).strftime('%Y-%m-%d')
        # Get last day of month
        if target_date.month == 12:
            next_month = target_date.replace(year=target_date.year + 1, month=1, day=1)
        else:
            next_month = target_date.replace(month=target_date.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Query Cost Explorer by service
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date,
                'End': end_date
            },
            Granularity='MONTHLY',
            Metrics=['BlendedCost'],
            GroupBy=[
                {
                    'Type': 'DIMENSION',
                    'Key': 'SERVICE'
                }
            ]
        )
        
        # Extract service costs
        services = []
        if response['ResultsByTime']:
            groups = response['ResultsByTime'][0]['Groups']
            for group in groups:
                service_name = group['Keys'][0]
                cost = float(group['Metrics']['BlendedCost']['Amount'])
                if cost > 0.01:  # Only include services with meaningful cost
                    services.append({
                        'service': service_name,
                        'cost': round(cost, 2)
                    })
        
        # Sort by cost descending
        services.sort(key=lambda x: x['cost'], reverse=True)
        
        result = {
            'services': services[:10],  # Top 10 services
            'period': f"{start_date} to {end_date}",
            'last_updated': datetime.now().isoformat()
        }
        
        # Cache for 1 hour
        cache_result(cache_key, result, 3600)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Error getting service costs: {str(e)}")
        return error_response(500, 'Failed to retrieve service costs')

def get_cost_trends():
    """Get daily cost trends for the last 30 days"""
    try:
        cache_key = f"cost_trends_{datetime.now().strftime('%Y-%m-%d-%H')}"
        
        # Check cache first
        cached = get_from_cache(cache_key)
        if cached:
            return success_response(cached)
        
        # Get last 30 days
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        # Query Cost Explorer
        response = ce_client.get_cost_and_usage(
            TimePeriod={
                'Start': start_date.strftime('%Y-%m-%d'),
                'End': end_date.strftime('%Y-%m-%d')
            },
            Granularity='DAILY',
            Metrics=['BlendedCost']
        )
        
        # Extract daily costs
        daily_costs = []
        for result in response['ResultsByTime']:
            date = result['TimePeriod']['Start']
            cost = float(result['Total']['BlendedCost']['Amount'])
            daily_costs.append({
                'date': date,
                'cost': round(cost, 2)
            })
        
        result = {
            'daily_costs': daily_costs,
            'period': f"Last 30 days",
            'last_updated': datetime.now().isoformat()
        }
        
        # Cache for 1 hour
        cache_result(cache_key, result, 3600)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Error getting cost trends: {str(e)}")
        return error_response(500, 'Failed to retrieve cost trends')

def get_costs_by_tag(month=None):
    """Get costs broken down by Service tag"""
    try:
        # Parse month parameter or use current month
        if month:
            # Validate month format
            if not re.match(r'^\d{4}-\d{2}$', month):
                raise ValueError("Invalid month format. Expected YYYY-MM")
            year, month_num = month.split('-')
            target_date = datetime(int(year), int(month_num), 1)
            cache_key = f"tag_costs_{month}_{datetime.now().strftime('%H')}"
        else:
            target_date = datetime.now()
            cache_key = f"tag_costs_{datetime.now().strftime('%Y-%m-%d-%H')}"
        
        # Check cache first
        cached = get_from_cache(cache_key)
        if cached:
            return success_response(cached)
        
        # Get month dates
        start_date = target_date.replace(day=1).strftime('%Y-%m-%d')
        # Get last day of month
        if target_date.month == 12:
            next_month = target_date.replace(year=target_date.year + 1, month=1, day=1)
        else:
            next_month = target_date.replace(month=target_date.month + 1, day=1)
        end_date = (next_month - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Try multiple common variations of service tag (case-sensitive in AWS)
        tag_variations = ['Service', 'service', 'SERVICE', 'app', 'App', 'application', 'Application', 'Project', 'project', 'PROJECT']
        all_services = {}
        
        for tag_key in tag_variations:
            try:
                response = ce_client.get_cost_and_usage(
                    TimePeriod={
                        'Start': start_date,
                        'End': end_date
                    },
                    Granularity='MONTHLY',
                    Metrics=['BlendedCost'],
                    GroupBy=[
                        {
                            'Type': 'TAG',
                            'Key': tag_key
                        }
                    ]
                )
        
                # Extract tag costs
                if response['ResultsByTime']:
                    groups = response['ResultsByTime'][0]['Groups']
                    for group in groups:
                        # Keys format: ['TagKey$tag-value'] or ['TagKey$'] for untagged
                        raw_key = group['Keys'][0] if group['Keys'] else f'{tag_key}$Untagged'
                        service_tag = raw_key.split('$')[1] if '$' in raw_key and len(raw_key.split('$')) > 1 else 'Untagged'
                        if not service_tag:  # Handle empty tag values
                            service_tag = 'Untagged'
                            
                        cost = float(group['Metrics']['BlendedCost']['Amount'])
                        if cost > 0.01:  # Only include meaningful costs
                            # Aggregate costs for same service names from different tag keys
                            if service_tag in all_services:
                                all_services[service_tag] += cost
                            else:
                                all_services[service_tag] = cost
                                
            except Exception as tag_error:
                logger.warning(f"Error querying tag '{tag_key}': {str(tag_error)}")
                continue
        
        # Convert to list format
        services = []
        for service_name, cost in all_services.items():
            services.append({
                'service': service_name,
                'cost': round(cost, 2)
            })
        
        # Sort by cost descending
        services.sort(key=lambda x: x['cost'], reverse=True)
        
        result = {
            'services': services[:10],  # Top 10 services by tag
            'period': f"{start_date} to {end_date}",
            'last_updated': datetime.now().isoformat()
        }
        
        # Cache for 1 hour
        cache_result(cache_key, result, 3600)
        
        return success_response(result)
        
    except Exception as e:
        logger.error(f"Error getting costs by tag: {str(e)}")
        return error_response(500, 'Failed to retrieve costs by tag')

def get_from_cache(cache_key):
    """Get data from DynamoDB cache"""
    try:
        response = table.get_item(Key={'cache_key': cache_key})
        if 'Item' in response:
            return json.loads(response['Item']['data'])
        return None
    except Exception as e:
        logger.warning(f"Cache read error: {str(e)}")
        return None

def cache_result(cache_key, data, ttl_seconds):
    """Store data in DynamoDB cache with TTL"""
    try:
        ttl = int((datetime.now() + timedelta(seconds=ttl_seconds)).timestamp())
        table.put_item(
            Item={
                'cache_key': cache_key,
                'data': json.dumps(data, default=str),
                'ttl': ttl
            }
        )
    except Exception as e:
        logger.warning(f"Cache write error: {str(e)}")

def success_response(data):
    """Return successful API response"""
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': 'http://localhost:3000',
            'Access-Control-Allow-Headers': 'content-type,authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps(data, default=str)
    }

def error_response(status_code, message):
    """Return error API response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': 'http://localhost:3000',
            'Access-Control-Allow-Headers': 'content-type,authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': json.dumps({'error': message})
    }

def cors_response():
    """Return CORS preflight response"""
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': 'http://localhost:3000',
            'Access-Control-Allow-Headers': 'content-type,authorization',
            'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
        },
        'body': ''
    }