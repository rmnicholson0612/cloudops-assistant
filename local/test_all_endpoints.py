#!/usr/bin/env python3
"""
Comprehensive endpoint testing for CloudOps Assistant LocalStack setup
Tests all SAM template endpoints to ensure they work with real Lambda functions
"""

import requests
import json
import time

BASE_URL = 'http://localhost:8080'
HEADERS = {
    'Authorization': 'Bearer mock-jwt-token-local-dev',
    'Content-Type': 'application/json'
}

def test_endpoint(method, path, data=None, expected_status=200):
    """Test an endpoint and return result"""
    url = f"{BASE_URL}{path}"
    try:
        if method == 'GET':
            response = requests.get(url, headers=HEADERS)
        elif method == 'POST':
            response = requests.post(url, headers=HEADERS, json=data)
        elif method == 'PUT':
            response = requests.put(url, headers=HEADERS, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=HEADERS)

        success = response.status_code == expected_status
        return {
            'success': success,
            'status': response.status_code,
            'response': response.json() if response.content else {}
        }
    except Exception as e:
        return {
            'success': False,
            'status': 'ERROR',
            'response': {'error': str(e)}
        }

def run_comprehensive_test():
    """Run comprehensive test of all endpoints"""
    print("🧪 CloudOps Assistant LocalStack Endpoint Testing")
    print("=" * 60)

    tests = [
        # Health check
        ('GET', '/health', None, 200),

        # Auth endpoints
        ('POST', '/auth/register', {'email': 'test@local.dev', 'password': 'password123'}, 200),
        ('POST', '/auth/login', {'email': 'test@local.dev', 'password': 'password123'}, 200),
        ('GET', '/auth/verify', None, 200),

        # Plan management
        ('POST', '/upload-plan', {
            'repo_name': 'test-repo',
            'github_target': 'test-user',
            'plan_content': 'Terraform will perform the following actions:\n\n+ aws_instance.web'
        }, 200),
        ('GET', '/plan-history/test-repo', None, 200),

        # Cost endpoints (mock data)
        ('GET', '/costs/current', None, 200),
        ('GET', '/costs/services', None, 200),
        ('GET', '/costs/trends', None, 200),
        ('GET', '/costs/by-tag', None, 200),

        # Budget management
        ('POST', '/budgets/configure', {
            'budget_name': 'Test Budget',
            'monthly_limit': 100.00,
            'thresholds': [50, 80, 100],
            'email': 'test@local.dev'
        }, 200),
        ('GET', '/budgets/status', None, 200),
        ('GET', '/budgets/alerts', None, 200),

        # Drift monitoring
        ('POST', '/drift/configure', {
            'repo_name': 'test-terraform-repo',
            'github_url': 'https://github.com/test/terraform-repo.git',
            'terraform_dir': '.',
            'schedule': 'daily',
            'alert_email': 'test@local.dev'
        }, 200),
        ('GET', '/drift/status', None, 200),

        # Repository scanning
        ('POST', '/scan-repos', {
            'github_target': 'test-user',
            'github_token': None
        }, 200),

        # AI endpoints (may fail without Bedrock)
        ('GET', '/ai/explanations', None, 200),

        # Postmortem management
        ('POST', '/postmortems', {
            'title': 'Test Incident',
            'service': 'test-service',
            'severity': 'medium',
            'start_time': '2024-01-01T00:00:00Z',
            'incident_summary': 'Test incident for LocalStack'
        }, 200),
        ('GET', '/postmortems', None, 200),

        # User management
        ('GET', '/users', None, 200),

        # Service documentation
        ('GET', '/docs/services', None, 200),
        ('POST', '/docs/register', {
            'service_name': 'test-service',
            'owner': 'test-user',
            'github_url': 'https://github.com/test/service'
        }, 200),

        # PR reviews
        ('GET', '/pr-reviews', None, 200),
        ('POST', '/pr-reviews/configure', {
            'repo_name': 'test-repo',
            'github_url': 'https://github.com/test/repo',
            'enabled': True
        }, 200),

        # Slack integration (may fail without Slack config)
        ('POST', '/slack/events', {'type': 'url_verification', 'challenge': 'test'}, 200),

        # Resource discovery (may fail without AWS resources)
        ('GET', '/discovery/scans', None, 200),
    ]

    passed = 0
    failed = 0

    for method, path, data, expected_status in tests:
        print(f"\n🔍 Testing {method} {path}")
        result = test_endpoint(method, path, data, expected_status)

        if result['success']:
            print(f"✅ PASS - Status: {result['status']}")
            passed += 1
        else:
            print(f"❌ FAIL - Status: {result['status']}")
            if 'error' in result['response']:
                print(f"   Error: {result['response']['error']}")
            failed += 1

        # Small delay between requests
        time.sleep(0.1)

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    print(f"🎯 Success Rate: {(passed/(passed+failed)*100):.1f}%")

    if failed == 0:
        print("🎉 All endpoints working with LocalStack!")
    else:
        print("⚠️  Some endpoints need attention")

    return passed, failed

if __name__ == '__main__':
    run_comprehensive_test()
