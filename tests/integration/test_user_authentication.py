"""
Integration tests for user authentication flow
Tests user creation, login, and endpoint access validation
"""
import json
import pytest
import requests
import time
from unittest.mock import patch, MagicMock
from .test_config import test_config
from .test_helpers import auth_helper, api_helper


class TestUserAuthentication:
    """Test user authentication flow including registration, login, and endpoint access"""

    @pytest.fixture
    def api_base_url(self):
        """Base URL for API from test configuration"""
        return test_config.api_base_url

    @pytest.fixture
    def test_user_credentials(self):
        """Test user credentials"""
        return test_config.get_test_user_credentials()

    @pytest.fixture
    def existing_user_credentials(self):
        """Existing user credentials for login tests"""
        return test_config.get_test_user_credentials("existing")

    def test_user_registration_success(self, api_base_url, test_user_credentials):
        """Test successful user registration"""
        response = requests.post(
            f"{api_base_url}/auth/register",
            json=test_user_credentials,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "User registered successfully"
        assert data["email"] == test_user_credentials["email"]

    def test_user_registration_duplicate_email(self, api_base_url, existing_user_credentials):
        """Test registration with existing email returns appropriate error"""
        # First registration
        requests.post(
            f"{api_base_url}/auth/register",
            json=existing_user_credentials,
            headers={"Content-Type": "application/json"}
        )

        # Attempt duplicate registration
        response = requests.post(
            f"{api_base_url}/auth/register",
            json=existing_user_credentials,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "User already exists"

    def test_user_registration_invalid_email(self, api_base_url):
        """Test registration with invalid email format"""
        invalid_credentials = {
            "email": "invalid-email",
            "password": "<test_password>"
        }

        response = requests.post(
            f"{api_base_url}/auth/register",
            json=invalid_credentials,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Invalid email format"

    def test_user_registration_missing_fields(self, api_base_url):
        """Test registration with missing required fields"""
        # Missing password
        response = requests.post(
            f"{api_base_url}/auth/register",
            json={"email": "test@example.com"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Email and password required"

        # Missing email
        response = requests.post(
            f"{api_base_url}/auth/register",
            json={"password": "<test_password>"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Email and password required"

    def test_user_login_success(self, api_base_url, test_user_credentials):
        """Test successful user login"""
        # First register the user
        requests.post(
            f"{api_base_url}/auth/register",
            json=test_user_credentials,
            headers={"Content-Type": "application/json"}
        )

        # Then login
        response = requests.post(
            f"{api_base_url}/auth/login",
            json=test_user_credentials,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Login successful"
        assert "access_token" in data
        assert "id_token" in data
        assert "refresh_token" in data
        assert "expires_in" in data

        # Verify token format (JWT should have 3 parts separated by dots)
        assert len(data["access_token"].split(".")) == 3

    def test_user_login_invalid_credentials(self, api_base_url):
        """Test login with invalid credentials"""
        invalid_credentials = {
            "email": "nonexistent@example.com",
            "password": "<test_password>"
        }

        response = requests.post(
            f"{api_base_url}/auth/login",
            json=invalid_credentials,
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "Invalid credentials"

    def test_user_login_missing_fields(self, api_base_url):
        """Test login with missing required fields"""
        # Missing password
        response = requests.post(
            f"{api_base_url}/auth/login",
            json={"email": "test@example.com"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Email and password required"

    def test_token_verification_success(self, api_base_url, test_user_credentials):
        """Test successful token verification"""
        # Register and login to get token
        requests.post(f"{api_base_url}/auth/register", json=test_user_credentials)
        login_response = requests.post(f"{api_base_url}/auth/login", json=test_user_credentials)
        token = login_response.json()["access_token"]

        # Verify token
        response = requests.post(
            f"{api_base_url}/auth/verify",
            json={"token": token},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert "username" in data
        assert "email" in data
        assert "user_id" in data

    def test_token_verification_invalid_token(self, api_base_url):
        """Test token verification with invalid token"""
        response = requests.post(
            f"{api_base_url}/auth/verify",
            json={"token": "invalid.jwt.token"},
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 401
        data = response.json()
        assert data["error"] == "Invalid or expired token"


class TestEndpointAccess:
    """Test endpoint access with and without authentication"""

    @pytest.fixture
    def api_base_url(self):
        return test_config.api_base_url

    @pytest.fixture
    def authenticated_headers(self):
        """Get authenticated headers with valid JWT token"""
        return auth_helper.get_authenticated_headers("endpoint-test")

    @pytest.fixture
    def unauthenticated_endpoints(self):
        """List of endpoints that should be accessible without authentication"""
        return test_config.unauthenticated_endpoints

    @pytest.fixture
    def authenticated_endpoints(self):
        """List of endpoints that require authentication"""
        return test_config.authenticated_endpoints

    def test_unauthenticated_endpoints_accessible(self, api_base_url, unauthenticated_endpoints):
        """Test that unauthenticated endpoints are accessible without token"""
        for endpoint, method in unauthenticated_endpoints:
            if method == "GET":
                response = requests.get(f"{api_base_url}{endpoint}")
            elif method == "POST":
                response = requests.post(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers={"Content-Type": "application/json"}
                )

            # Should not return 401 Unauthorized (may return other errors like 400 for missing data)
            assert response.status_code != 401, f"Endpoint {endpoint} should not require authentication"

    def test_authenticated_endpoints_require_auth(self, api_base_url, authenticated_endpoints):
        """Test that authenticated endpoints return 401 without valid token"""
        for endpoint, method in authenticated_endpoints:
            if method == "GET":
                response = requests.get(f"{api_base_url}{endpoint}")
            elif method == "POST":
                response = requests.post(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers={"Content-Type": "application/json"}
                )
            elif method == "PUT":
                response = requests.put(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers={"Content-Type": "application/json"}
                )
            elif method == "DELETE":
                response = requests.delete(f"{api_base_url}{endpoint}")

            assert response.status_code == 401, f"Endpoint {endpoint} should require authentication"

            # Verify error message
            try:
                data = response.json()
                assert "error" in data
            except json.JSONDecodeError:
                pass  # Some endpoints might not return JSON

    def test_authenticated_endpoints_with_valid_token(self, api_base_url, authenticated_endpoints, authenticated_headers):
        """Test that authenticated endpoints are accessible with valid token"""
        for endpoint, method in authenticated_endpoints:
            if method == "GET":
                response = requests.get(f"{api_base_url}{endpoint}", headers=authenticated_headers)
            elif method == "POST":
                response = requests.post(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers=authenticated_headers
                )
            elif method == "PUT":
                response = requests.put(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers=authenticated_headers
                )
            elif method == "DELETE":
                response = requests.delete(f"{api_base_url}{endpoint}", headers=authenticated_headers)

            # Should not return 401 Unauthorized (may return other errors like 400 for missing data)
            assert response.status_code != 401, f"Endpoint {endpoint} should be accessible with valid token"

    def test_authenticated_endpoints_with_invalid_token(self, api_base_url, authenticated_endpoints):
        """Test that authenticated endpoints return 401 with invalid token"""
        invalid_headers = {
            "Authorization": "Bearer invalid.jwt.token",
            "Content-Type": "application/json"
        }

        for endpoint, method in authenticated_endpoints:
            if method == "GET":
                response = requests.get(f"{api_base_url}{endpoint}", headers=invalid_headers)
            elif method == "POST":
                response = requests.post(
                    f"{api_base_url}{endpoint}",
                    json={},
                    headers=invalid_headers
                )

            assert response.status_code == 401, f"Endpoint {endpoint} should reject invalid token"

    def test_cors_headers_present(self, api_base_url):
        """Test that CORS headers are present in responses"""
        response = requests.options(f"{api_base_url}/auth/login")

        assert "Access-Control-Allow-Origin" in response.headers
        assert "Access-Control-Allow-Headers" in response.headers
        assert "Access-Control-Allow-Methods" in response.headers

        # Verify JWT-compatible headers
        allowed_headers = response.headers.get("Access-Control-Allow-Headers", "")
        assert "Authorization" in allowed_headers


class TestUserAuthenticationMocked:
    """Mocked tests for user authentication when AWS services are not available"""

    @patch('boto3.client')
    def test_register_user_mocked(self, mock_boto_client):
        """Test user registration with mocked Cognito"""
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))
        from auth_handler import register_user

        # Mock Cognito client
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        # Mock successful registration
        mock_cognito.admin_create_user.return_value = {}
        mock_cognito.admin_set_user_password.return_value = {}

        # Test event
        event = {
            "body": json.dumps({
                "email": "test@example.com",
                "password": "<test_password>"
            })
        }

        with patch.dict('os.environ', {'USER_POOL_ID': 'test-pool-id'}):
            response = register_user(event)

        assert response["statusCode"] == 200
        data = json.loads(response["body"])
        assert data["message"] == "User registered successfully"
        assert data["email"] == "test@example.com"

    @patch('boto3.client')
    def test_login_user_mocked(self, mock_boto_client):
        """Test user login with mocked Cognito"""
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))
        from auth_handler import login_user

        # Mock Cognito client
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        # Mock successful login
        mock_cognito.admin_initiate_auth.return_value = {
            "AuthenticationResult": {
                "AccessToken": "mock.access.token",
                "IdToken": "mock.id.token",
                "RefreshToken": "mock.refresh.token",
                "ExpiresIn": 3600
            }
        }

        # Test event
        event = {
            "body": json.dumps({
                "email": "test@example.com",
                "password": "<test_password>"
            })
        }

        with patch.dict('os.environ', {
            'USER_POOL_ID': 'test-pool-id',
            'USER_POOL_CLIENT_ID': 'test-client-id'
        }):
            response = login_user(event)

        assert response["statusCode"] == 200
        data = json.loads(response["body"])
        assert data["message"] == "Login successful"
        assert data["access_token"] == "mock.access.token"

    @patch('boto3.client')
    def test_verify_token_mocked(self, mock_boto_client):
        """Test token verification with mocked Cognito"""
        import sys
        import os
        sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))
        from auth_handler import verify_token

        # Mock Cognito client
        mock_cognito = MagicMock()
        mock_boto_client.return_value = mock_cognito

        # Mock successful token verification
        mock_cognito.get_user.return_value = {
            "Username": "test@example.com",
            "UserAttributes": [
                {"Name": "email", "Value": "test@example.com"},
                {"Name": "sub", "Value": "test-user-id"}
            ]
        }

        # Test event
        event = {
            "body": json.dumps({
                "token": "mock.jwt.token"
            })
        }

        response = verify_token(event)

        assert response["statusCode"] == 200
        data = json.loads(response["body"])
        assert data["valid"] is True
        assert data["email"] == "test@example.com"
        assert data["user_id"] == "test-user-id"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
