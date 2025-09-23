"""
Test helper utilities for integration tests
Provides common functions for authentication and API testing
"""
import json
import time
import requests
from typing import Dict, Optional, Tuple
from .test_config import test_config


class AuthTestHelper:
    """Helper class for authentication-related test operations"""

    def __init__(self, api_base_url: str = None):
        self.api_base_url = api_base_url or test_config.api_base_url
        self._cached_tokens = {}

    def create_test_user(self, suffix: str = "") -> Dict[str, str]:
        """Create a new test user and return credentials"""
        credentials = test_config.get_test_user_credentials(suffix)

        response = requests.post(
            f"{self.api_base_url}/auth/register",
            json=credentials,
            headers={"Content-Type": "application/json"},
            timeout=test_config.test_timeout
        )

        if response.status_code == 200:
            return credentials
        elif response.status_code == 400 and "already exists" in response.text:
            # User already exists, return credentials anyway
            return credentials
        else:
            raise Exception(f"Failed to create test user: {response.status_code} - {response.text}")

    def login_user(self, credentials: Dict[str, str]) -> Dict[str, str]:
        """Login user and return authentication tokens"""
        response = requests.post(
            f"{self.api_base_url}/auth/login",
            json=credentials,
            headers={"Content-Type": "application/json"},
            timeout=test_config.test_timeout
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to login user: {response.status_code} - {response.text}")

    def get_authenticated_headers(self, user_suffix: str = "") -> Dict[str, str]:
        """Get authenticated headers for API requests"""
        cache_key = f"user_{user_suffix}"

        if cache_key in self._cached_tokens:
            token_data = self._cached_tokens[cache_key]
            # Check if token is still valid (simple time-based check)
            if time.time() - token_data["created_at"] < 3000:  # 50 minutes
                return test_config.get_auth_headers(token_data["access_token"])

        # Create new user and login
        credentials = self.create_test_user(user_suffix)
        token_data = self.login_user(credentials)

        # Cache token
        self._cached_tokens[cache_key] = {
            "access_token": token_data["access_token"],
            "created_at": time.time()
        }

        return test_config.get_auth_headers(token_data["access_token"])

    def verify_token(self, token: str) -> Dict[str, str]:
        """Verify JWT token and return user info"""
        response = requests.post(
            f"{self.api_base_url}/auth/verify",
            json={"token": token},
            headers={"Content-Type": "application/json"},
            timeout=test_config.test_timeout
        )

        if response.status_code == 200:
            return response.json()
        else:
            raise Exception(f"Failed to verify token: {response.status_code} - {response.text}")

    def cleanup_test_users(self):
        """Clean up cached tokens (actual user cleanup would require admin permissions)"""
        self._cached_tokens.clear()


class APITestHelper:
    """Helper class for API testing operations"""

    def __init__(self, api_base_url: str = None):
        self.api_base_url = api_base_url or test_config.api_base_url
        self.auth_helper = AuthTestHelper(api_base_url)

    def test_endpoint_requires_auth(self, endpoint: str, method: str = "GET") -> bool:
        """Test if an endpoint requires authentication"""
        response = self._make_request(endpoint, method)
        return response.status_code == 401

    def test_endpoint_with_auth(self, endpoint: str, method: str = "GET",
                               data: Dict = None, user_suffix: str = "") -> requests.Response:
        """Test endpoint with authentication"""
        headers = self.auth_helper.get_authenticated_headers(user_suffix)
        return self._make_request(endpoint, method, data, headers)

    def test_endpoint_without_auth(self, endpoint: str, method: str = "GET",
                                  data: Dict = None) -> requests.Response:
        """Test endpoint without authentication"""
        return self._make_request(endpoint, method, data)

    def _make_request(self, endpoint: str, method: str, data: Dict = None,
                     headers: Dict = None) -> requests.Response:
        """Make HTTP request to endpoint"""
        url = f"{self.api_base_url}{endpoint}"
        default_headers = {"Content-Type": "application/json"}

        if headers:
            default_headers.update(headers)

        request_kwargs = {
            "headers": default_headers,
            "timeout": test_config.test_timeout
        }

        if data:
            request_kwargs["json"] = data

        if method.upper() == "GET":
            return requests.get(url, **request_kwargs)
        elif method.upper() == "POST":
            return requests.post(url, **request_kwargs)
        elif method.upper() == "PUT":
            return requests.put(url, **request_kwargs)
        elif method.upper() == "DELETE":
            return requests.delete(url, **request_kwargs)
        elif method.upper() == "OPTIONS":
            return requests.options(url, **request_kwargs)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

    def verify_cors_headers(self, endpoint: str) -> bool:
        """Verify CORS headers are present and correct"""
        response = self._make_request(endpoint, "OPTIONS")
        expected_headers = test_config.get_cors_headers()

        for header_name, expected_value in expected_headers.items():
            actual_value = response.headers.get(header_name)
            if not actual_value:
                return False

            # For Allow-Headers and Allow-Methods, check if expected values are present
            if header_name in ["Access-Control-Allow-Headers", "Access-Control-Allow-Methods"]:
                expected_items = expected_value.split(",")
                actual_items = actual_value.split(",")
                for item in expected_items:
                    if item.strip() not in [a.strip() for a in actual_items]:
                        return False
            elif actual_value != expected_value:
                return False

        return True

    def batch_test_endpoints(self, endpoints: list, require_auth: bool = True,
                           user_suffix: str = "") -> Dict[str, Dict]:
        """Test multiple endpoints and return results"""
        results = {}

        for endpoint, method in endpoints:
            try:
                if require_auth:
                    response = self.test_endpoint_with_auth(endpoint, method, user_suffix=user_suffix)
                else:
                    response = self.test_endpoint_without_auth(endpoint, method)

                results[f"{method} {endpoint}"] = {
                    "status_code": response.status_code,
                    "success": response.status_code < 500,  # Not a server error
                    "requires_auth": response.status_code == 401 if not require_auth else None
                }
            except Exception as e:
                results[f"{method} {endpoint}"] = {
                    "status_code": None,
                    "success": False,
                    "error": str(e)
                }

        return results


class MockTestHelper:
    """Helper class for mocked tests when AWS services are not available"""

    @staticmethod
    def mock_cognito_success_response():
        """Mock successful Cognito responses"""
        return {
            "admin_create_user": {},
            "admin_set_user_password": {},
            "admin_initiate_auth": {
                "AuthenticationResult": {
                    "AccessToken": "mock.access.token",
                    "IdToken": "mock.id.token",
                    "RefreshToken": "mock.refresh.token",
                    "ExpiresIn": 3600
                }
            },
            "get_user": {
                "Username": "test@example.com",
                "UserAttributes": [
                    {"Name": "email", "Value": "test@example.com"},
                    {"Name": "sub", "Value": "test-user-id"}
                ]
            }
        }

    @staticmethod
    def mock_environment_variables():
        """Mock environment variables for testing"""
        return {
            "USER_POOL_ID": "test-pool-id",
            "USER_POOL_CLIENT_ID": "test-client-id",
            "TERRAFORM_PLANS_TABLE": "test-plans-table",
            "COST_CACHE_TABLE": "test-cost-cache-table",
            "BUDGET_CONFIG_TABLE": "test-budget-config-table",
            "DRIFT_CONFIG_TABLE": "test-drift-config-table"
        }


# Global helper instances
auth_helper = AuthTestHelper()
api_helper = APITestHelper()
mock_helper = MockTestHelper()
