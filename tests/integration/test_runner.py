"""
Test runner for integration tests
Validates test setup and provides debugging information
"""
import os
import sys
import pytest
from .test_config import test_config
from .test_helpers import auth_helper, api_helper


def validate_test_environment():
    """Validate test environment setup"""
    print("=== CloudOps Assistant Integration Test Environment ===")
    print(f"API Base URL: {test_config.api_base_url}")
    print(f"Test Timeout: {test_config.test_timeout}s")
    print(f"Unauthenticated Endpoints: {len(test_config.unauthenticated_endpoints)}")
    print(f"Authenticated Endpoints: {len(test_config.authenticated_endpoints)}")

    # Check if API is accessible
    try:
        import requests
        response = requests.get(f"{test_config.api_base_url}/auth/register", timeout=5)
        print(f"API Connectivity: ✓ (Status: {response.status_code})")
    except Exception as e:
        print(f"API Connectivity: ✗ (Error: {str(e)})")

    print("\n=== Environment Variables ===")
    env_vars = [
        "CLOUDOPS_TEST_API_URL",
        "AWS_REGION",
        "AWS_PROFILE",
        "USER_POOL_ID",
        "USER_POOL_CLIENT_ID"
    ]

    for var in env_vars:
        value = os.environ.get(var, "Not Set")
        # Mask sensitive values
        if "ID" in var and value != "Not Set":
            value = f"{value[:8]}..."
        print(f"{var}: {value}")

    print("\n=== Test Configuration ===")
    print("Unauthenticated Endpoints:")
    for endpoint, method in test_config.unauthenticated_endpoints:
        print(f"  {method} {endpoint}")

    print("\nAuthenticated Endpoints (first 10):")
    for endpoint, method in test_config.authenticated_endpoints[:10]:
        print(f"  {method} {endpoint}")
    if len(test_config.authenticated_endpoints) > 10:
        print(f"  ... and {len(test_config.authenticated_endpoints) - 10} more")


def run_basic_connectivity_test():
    """Run basic connectivity test"""
    print("\n=== Basic Connectivity Test ===")

    try:
        # Test unauthenticated endpoint
        response = api_helper.test_endpoint_without_auth("/auth/register", "POST", {
            "email": "connectivity-test@example.com",
            "password": "TestPassword123!"
        })

        if response.status_code in [200, 400]:  # 400 is OK for validation errors
            print("✓ Unauthenticated endpoint accessible")
        else:
            print(f"✗ Unauthenticated endpoint failed: {response.status_code}")

        # Test CORS headers
        if api_helper.verify_cors_headers("/auth/login"):
            print("✓ CORS headers configured correctly")
        else:
            print("✗ CORS headers missing or incorrect")

    except Exception as e:
        print(f"✗ Connectivity test failed: {str(e)}")


def run_mock_tests():
    """Run mocked authentication tests"""
    print("\n=== Running Mocked Authentication Tests ===")

    # Run only the mocked tests
    exit_code = pytest.main([
        "tests/integration/test_user_authentication.py::TestUserAuthenticationMocked",
        "-v",
        "--tb=short"
    ])

    if exit_code == 0:
        print("✓ Mocked authentication tests passed")
    else:
        print("✗ Mocked authentication tests failed")

    return exit_code


def main():
    """Main test runner"""
    print("CloudOps Assistant Integration Test Runner")
    print("=" * 50)

    # Validate environment
    validate_test_environment()

    # Run basic connectivity test
    run_basic_connectivity_test()

    # Run mocked tests (these should always work)
    mock_exit_code = run_mock_tests()

    print("\n=== Test Runner Summary ===")
    if mock_exit_code == 0:
        print("✓ Basic test infrastructure is working")
        print("✓ Ready to run full integration tests with: make test-auth")
    else:
        print("✗ Test infrastructure has issues")
        print("✗ Check test setup and dependencies")

    return mock_exit_code


if __name__ == "__main__":
    sys.exit(main())
