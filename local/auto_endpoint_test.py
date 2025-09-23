#!/usr/bin/env python3
"""
Auto-discovery endpoint testing for CloudOps Assistant
Automatically discovers endpoints from SAM template and tests them
"""

import yaml
import requests
import json
import time
from pathlib import Path

BASE_URL = 'http://localhost:8080'
HEADERS = {
    'Authorization': 'Bearer mock-jwt-token-local-dev',
    'Content-Type': 'application/json'
}

def discover_endpoints_from_sam():
    """Discover all API endpoints from SAM template"""
    template_path = Path('../template.yaml')

    if not template_path.exists():
        print("SAM template not found")
        return []

    with open(template_path, 'r') as f:
        template = yaml.safe_load(f)

    endpoints = []
    resources = template.get('Resources', {})

    for resource_name, resource in resources.items():
        if resource.get('Type') == 'AWS::Serverless::Function':
            events = resource.get('Properties', {}).get('Events', {})

            for event_name, event in events.items():
                if event.get('Type') == 'Api':
                    props = event.get('Properties', {})
                    path = props.get('Path', '')
                    method = props.get('Method', '').upper()

                    if path and method:
                        endpoints.append({
                            'function': resource_name,
                            'event': event_name,
                            'method': method,
                            'path': path,
                            'handler': resource.get('Properties', {}).get('Handler', '')
                        })

    return endpoints

def generate_test_data(method, path):
    """Generate appropriate test data based on endpoint"""
    if method == 'GET':
        return None

    # Generate test data based on path patterns
    if '/auth/register' in path:
        return {'email': 'test@local.dev', 'password': 'password123'}
    elif '/auth/login' in path:
        return {'email': 'test@local.dev', 'password': 'password123'}
    elif '/upload-plan' in path:
        return {
            'repo_name': 'test-repo',
            'github_target': 'test-user',
            'plan_content': 'Terraform will perform the following actions:\n\n+ aws_instance.web'
        }
    elif '/budgets/configure' in path:
        return {
            'budget_name': 'Test Budget',
            'monthly_limit': 100.00,
            'thresholds': [50, 80, 100],
            'email': 'test@local.dev'
        }
    elif '/drift/configure' in path:
        return {
            'repo_name': 'test-terraform-repo',
            'github_url': 'https://github.com/test/terraform-repo.git',
            'terraform_dir': '.',
            'schedule': 'daily',
            'alert_email': 'test@local.dev'
        }
    elif '/scan-repos' in path:
        return {'github_target': 'test-user', 'github_token': None}
    elif '/postmortems' in path and method == 'POST':
        return {
            'title': 'Test Incident',
            'service': 'test-service',
            'severity': 'medium',
            'start_time': '2024-01-01T00:00:00Z',
            'incident_summary': 'Test incident for LocalStack'
        }
    elif '/docs/register' in path:
        return {
            'service_name': 'test-service',
            'owner': 'test-user',
            'github_url': 'https://github.com/test/service'
        }
    elif '/pr-reviews/configure' in path:
        return {
            'repo_name': 'test-repo',
            'github_url': 'https://github.com/test/repo',
            'enabled': True
        }
    elif '/slack/events' in path:
        return {'type': 'url_verification', 'challenge': 'test'}

    # Default minimal test data
    return {'test': True}

def test_endpoint(method, path, data=None):
    """Test an endpoint and return result"""
    url = f"{BASE_URL}{path}"
    try:
        if method == 'GET':
            response = requests.get(url, headers=HEADERS, timeout=10)
        elif method == 'POST':
            response = requests.post(url, headers=HEADERS, json=data, timeout=10)
        elif method == 'PUT':
            response = requests.put(url, headers=HEADERS, json=data, timeout=10)
        elif method == 'DELETE':
            response = requests.delete(url, headers=HEADERS, timeout=10)
        elif method == 'OPTIONS':
            response = requests.options(url, headers=HEADERS, timeout=10)
        else:
            return {'success': False, 'status': 'UNSUPPORTED_METHOD', 'response': {}}

        # Consider 2xx and 4xx as "working" (endpoint exists and responds)
        success = 200 <= response.status_code < 500

        try:
            response_data = response.json() if response.content else {}
        except:
            response_data = {'raw': response.text[:200]}

        return {
            'success': success,
            'status': response.status_code,
            'response': response_data
        }
    except requests.exceptions.Timeout:
        return {'success': False, 'status': 'TIMEOUT', 'response': {'error': 'Request timeout'}}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'status': 'CONNECTION_ERROR', 'response': {'error': 'Connection failed'}}
    except Exception as e:
        return {'success': False, 'status': 'ERROR', 'response': {'error': str(e)}}

def run_auto_discovery_test():
    """Run auto-discovery endpoint testing"""
    print("CloudOps Assistant Auto-Discovery Endpoint Testing")
    print("=" * 60)

    # Discover endpoints from SAM template
    print("Discovering endpoints from SAM template...")
    endpoints = discover_endpoints_from_sam()

    if not endpoints:
        print("No endpoints discovered from SAM template")
        return 0, 1

    print(f"Discovered {len(endpoints)} endpoints")

    passed = 0
    failed = 0
    results = []

    for endpoint in endpoints:
        method = endpoint['method']
        path = endpoint['path']
        function = endpoint['function']

        print(f"\nTesting {method} {path} ({function})")

        # Generate appropriate test data
        test_data = generate_test_data(method, path)

        # Test the endpoint
        result = test_endpoint(method, path, test_data)

        if result['success']:
            print(f"PASS - Status: {result['status']}")
            passed += 1
        else:
            print(f"FAIL - Status: {result['status']}")
            if 'error' in result['response']:
                print(f"   Error: {result['response']['error']}")
            failed += 1

        results.append({
            'endpoint': endpoint,
            'result': result
        })

        # Small delay between requests
        time.sleep(0.1)

    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print(f"Success Rate: {(passed/(passed+failed)*100):.1f}%")

    # Show summary by function
    print("\nResults by Function:")
    function_results = {}
    for item in results:
        func = item['endpoint']['function']
        if func not in function_results:
            function_results[func] = {'passed': 0, 'failed': 0}

        if item['result']['success']:
            function_results[func]['passed'] += 1
        else:
            function_results[func]['failed'] += 1

    for func, counts in function_results.items():
        total = counts['passed'] + counts['failed']
        rate = (counts['passed'] / total * 100) if total > 0 else 0
        print(f"  {func}: {counts['passed']}/{total} ({rate:.0f}%)")

    if failed == 0:
        print("\nAll discovered endpoints working!")
    else:
        print("\nSome endpoints need attention")

    return passed, failed

if __name__ == '__main__':
    run_auto_discovery_test()
