"""
Unit tests for auth_utils module
"""

import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

# Add backend/lambda to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from auth_utils import verify_jwt_token, verify_token, auth_required


class TestAuthUtils:
    """Test authentication utilities"""

    @patch('auth_utils.cognito_client')
    def test_verify_jwt_token_valid(self, mock_cognito):
        """Test verifying valid JWT token"""
        # Mock Cognito response
        mock_cognito.get_user.return_value = {
            'Username': 'testuser',
            'UserAttributes': [
                {'Name': 'sub', 'Value': 'test-user-123'},
                {'Name': 'email', 'Value': 'test@example.com'}
            ]
        }

        event = {'headers': {'Authorization': 'Bearer valid.token'}}
        user_info, error = verify_jwt_token(event)

        assert error is None
        assert user_info['user_id'] == 'test-user-123'
        assert user_info['email'] == 'test@example.com'
        assert user_info['username'] == 'testuser'

    def test_verify_jwt_token_missing_header(self):
        """Test handling missing authorization header"""
        event = {'headers': {}}
        user_info, error = verify_jwt_token(event)

        assert user_info is None
        assert error == 'Authorization header missing'

    def test_verify_jwt_token_local_dev(self):
        """Test local development token bypass"""
        event = {'headers': {'Authorization': 'Bearer mock-jwt-token-local-dev'}}
        user_info, error = verify_jwt_token(event)

        assert error is None
        assert user_info['user_id'] == 'local-user'
        assert user_info['email'] == 'test@local.dev'

    def test_auth_required_decorator_with_valid_token(self):
        """Test auth_required decorator with valid token"""
        @auth_required
        def test_function(event, context):
            return {"statusCode": 200, "body": "success"}

        event = {
            "headers": {"Authorization": "Bearer valid.token"},
            "httpMethod": "GET"
        }

        with patch('auth_utils.verify_jwt_token') as mock_verify:
            mock_verify.return_value = ({'user_id': 'test-user-123'}, None)

            result = test_function(event, {})

            assert result["statusCode"] == 200
            assert event["user_info"]["user_id"] == "test-user-123"

    def test_auth_required_decorator_missing_token(self):
        """Test auth_required decorator with missing token"""
        @auth_required
        def test_function(event, context):
            return {"statusCode": 200}

        event = {"headers": {}, "httpMethod": "GET"}

        result = test_function(event, {})

        # When bypass is enabled, should return 200 with mock user info
        if os.environ.get('BYPASS_AUTH_FOR_TESTS') == 'true':
            assert result["statusCode"] == 200
            assert event["user_info"]["user_id"] == "test-user-123"
        else:
            assert result["statusCode"] == 401
            assert "Authorization header missing" in result["body"]

    def test_auth_required_decorator_invalid_token(self):
        """Test auth_required decorator with invalid token"""
        @auth_required
        def test_function(event, context):
            return {"statusCode": 200}

        event = {
            "headers": {"Authorization": "Bearer invalid.token"},
            "httpMethod": "GET"
        }

        with patch('auth_utils.verify_jwt_token') as mock_verify:
            mock_verify.return_value = (None, 'Invalid token')

            result = test_function(event, {})

            # When bypass is enabled, should return 200 with mock user info
            if os.environ.get('BYPASS_AUTH_FOR_TESTS') == 'true':
                assert result["statusCode"] == 200
                assert event["user_info"]["user_id"] == "test-user-123"
            else:
                assert result["statusCode"] == 401

    def test_verify_jwt_token_invalid_format(self):
        """Test invalid authorization format"""
        event = {'headers': {'Authorization': 'InvalidFormat token'}}
        user_info, error = verify_jwt_token(event)

        assert user_info is None
        assert error == 'Invalid authorization format'

    @patch('auth_utils.cognito_client')
    def test_verify_jwt_token_not_authorized(self, mock_cognito):
        """Test NotAuthorizedException handling"""
        from botocore.exceptions import ClientError

        # Create a proper exception class
        class NotAuthorizedException(Exception):
            pass

        mock_cognito.exceptions.NotAuthorizedException = NotAuthorizedException
        mock_cognito.get_user.side_effect = NotAuthorizedException('Not authorized')

        event = {'headers': {'Authorization': 'Bearer expired.token'}}
        user_info, error = verify_jwt_token(event)

        assert user_info is None
        assert error == 'Invalid or expired token'

    @patch('auth_utils.cognito_client')
    @patch('auth_utils.logger')
    def test_verify_jwt_token_general_exception(self, mock_logger, mock_cognito):
        """Test general exception handling"""
        # Mock the exceptions attribute properly
        class MockExceptions:
            class NotAuthorizedException(Exception):
                pass

        mock_cognito.exceptions = MockExceptions()
        mock_cognito.get_user.side_effect = ValueError('Network error')

        event = {'headers': {'Authorization': 'Bearer valid.token'}}
        user_info, error = verify_jwt_token(event)

        assert user_info is None
        assert error == 'Token verification failed'
        mock_logger.error.assert_called_once()

    @patch('auth_utils.cognito_client')
    def test_verify_token_success(self, mock_cognito):
        """Test verify_token function success"""
        mock_cognito.get_user.return_value = {
            'Username': 'testuser',
            'UserAttributes': [
                {'Name': 'sub', 'Value': 'test-user-123'},
                {'Name': 'email', 'Value': 'test@example.com'}
            ]
        }

        result = verify_token('valid.token')

        assert result['user_id'] == 'test-user-123'
        assert result['email'] == 'test@example.com'
        assert result['username'] == 'testuser'

    @patch('auth_utils.cognito_client')
    def test_verify_token_exception(self, mock_cognito):
        """Test verify_token function exception handling"""
        mock_cognito.get_user.side_effect = Exception('Error')

        result = verify_token('invalid.token')

        assert result is None

    def test_verify_jwt_token_case_insensitive_header(self):
        """Test case insensitive authorization header"""
        event = {'headers': {'authorization': 'Bearer mock-jwt-token-local-dev'}}
        user_info, error = verify_jwt_token(event)

        assert error is None
        assert user_info['user_id'] == 'local-user'
