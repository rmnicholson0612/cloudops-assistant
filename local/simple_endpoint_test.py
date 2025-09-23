#!/usr/bin/env python3
"""
Simple endpoint connectivity test for CloudOps Assistant
Tests basic connectivity without parsing SAM template
"""

import requests
import json
import time

BASE_URL = 'http://localhost:8080'
HEADERS = {
    'Authorization': 'Bearer mock-jwt-token-local-dev',
    'Content-Type': 'application/json'
}

# Core endpoints to test
TEST_ENDPOINTS = [
    {'method': 'GET', 'path': '/health', 'data': None},
    {'method': 'GET', 'path': '/costs', 'data': None},
    {'method': 'GET', 'path': '/plans', 'data': None},
    {'method': 'POST', 'path': '/upload-plan', 'data': {
        'repo_name': 'test-repo',
        'github_target': 'test-user',
        'plan_content': 'Terraform will perform the following actions:\n\n+ aws_instance.web'
    }},
    {'method': 'POST', 'path': '/scan-repos', 'data': {
        'github_target': 'test-user',
        'github_token': None
    }},
]

def test_endpoint(method, path, data=None):
    """Test an endpoint and return result"""
    url = f"{BASE_URL}{path}"
    try:
        if method == 'GET':
            response = requests.get(url, headers=HEADERS, timeout=5)
        elif method == 'POST':
            response = requests.post(url, headers=HEADERS, json=data, timeout=5)
        else:
            return {'success': False, 'status': 'UNSUPPORTED_METHOD'}

        # Only consider 2xx as success - 401/403 indicate auth failure
        if response.status_code == 401:
            return {'success': False, 'status': 401, 'error': 'UNAUTHORIZED'}
        elif response.status_code == 403:
            return {'success': False, 'status': 403, 'error': 'FORBIDDEN'}

        success = 200 <= response.status_code < 300

        return {
            'success': success,
            'status': response.status_code,
            'response': response.text[:100] if response.text else ''
        }
    except requests.exceptions.Timeout:
        return {'success': False, 'status': 'TIMEOUT'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'status': 'CONNECTION_ERROR'}
    except Exception as e:
        return {'success': False, 'status': 'ERROR', 'error': str(e)}

def run_simple_test():
    """Run simple connectivity test"""
    print("CloudOps Assistant Simple Connectivity Test")
    print("=" * 50)

    passed = 0
    failed = 0

    for endpoint in TEST_ENDPOINTS:
        method = endpoint['method']
        path = endpoint['path']
        data = endpoint['data']

        print(f"\nTesting {method} {path}")

        result = test_endpoint(method, path, data)

        if result['success']:
            print(f"PASS - Status: {result['status']}")
            passed += 1
        else:
            status = result['status']
            if status in [401, 403]:
                print(f"AUTH FAIL - Status: {status} (Check authorization)")
            else:
                print(f"FAIL - Status: {status}")
            if 'error' in result:
                print(f"   Error: {result['error']}")
            failed += 1

        time.sleep(0.1)

    print("\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("All basic endpoints working!")
    else:
        print("Some endpoints need attention")

    return passed, failed

if __name__ == '__main__':
    run_simple_test()
