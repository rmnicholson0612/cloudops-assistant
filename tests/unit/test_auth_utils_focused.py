
import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from auth_utils import verify_jwt_token, verify_token, auth_required

class TestAuthUtilsFocused:
    def test_verify_jwt_token_missing_header(self):
        event = {'headers': {}}
        user_info, error = verify_jwt_token(event)
        assert user_info is None
        assert error == 'Authorization header missing'

    def test_verify_jwt_token_case_insensitive(self):
        event = {'headers': {'authorization': 'Bearer mock-jwt-token-local-dev'}}
        user_info, error = verify_jwt_token(event)
        assert error is None
        assert user_info['user_id'] == 'local-user'

    def test_verify_jwt_token_invalid_format(self):
        event = {'headers': {'Authorization': 'InvalidFormat token'}}
        user_info, error = verify_jwt_token(event)
        assert user_info is None
        assert error == 'Invalid authorization format'

    def test_verify_jwt_token_local_dev(self):
        event = {'headers': {'Authorization': 'Bearer mock-jwt-token-local-dev'}}
        user_info, error = verify_jwt_token(event)
        assert error is None
        assert user_info['user_id'] == 'local-user'
        assert user_info['email'] == 'test@local.dev'

    @patch('auth_utils.cognito_client')
    def test_verify_jwt_token_cognito_success(self, mock_cognito):
        mock_cognito.get_user.return_value = {
            'Username': 'testuser',
            'UserAttributes': [
                {'Name': 'sub', 'Value': 'user123'},
                {'Name': 'email', 'Value': 'test@example.com'}
            ]
        }

        event = {'headers': {'Authorization': 'Bearer valid.token'}}
        user_info, error = verify_jwt_token(event)

        assert error is None
        assert user_info['user_id'] == 'user123'
        assert user_info['email'] == 'test@example.com'
        assert user_info['username'] == 'testuser'

    @patch('auth_utils.cognito_client')
    def test_verify_jwt_token_not_authorized(self, mock_cognito):
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
        mock_cognito.get_user.return_value = {
            'Username': 'testuser',
            'UserAttributes': [
                {'Name': 'sub', 'Value': 'user123'},
                {'Name': 'email', 'Value': 'test@example.com'}
            ]
        }

        result = verify_token('valid.token')
        assert result['user_id'] == 'user123'
        assert result['email'] == 'test@example.com'
        assert result['username'] == 'testuser'

    @patch('auth_utils.cognito_client')
    def test_verify_token_exception(self, mock_cognito):
        mock_cognito.get_user.side_effect = Exception('Error')
        result = verify_token('invalid.token')
        assert result is None

    def test_auth_required_bypass_enabled(self):
        @auth_required
        def test_handler(event, context):
            return {"statusCode": 200, "user_id": event["user_info"]["user_id"]}

        event = {}
        result = test_handler(event, {})
        assert result["statusCode"] == 200
        assert result["user_id"] == "test-user-123"

    @patch.dict(os.environ, {'BYPASS_AUTH_FOR_TESTS': 'false'})
    @patch('auth_utils.verify_jwt_token')
    def test_auth_required_normal_flow_success(self, mock_verify):
        mock_verify.return_value = ({'user_id': 'user123'}, None)

        @auth_required
        def test_handler(event, context):
            return {"statusCode": 200, "user_id": event["user_info"]["user_id"]}

        event = {'headers': {'Authorization': 'Bearer valid.token'}}
        result = test_handler(event, {})
        assert result["statusCode"] == 200
        assert result["user_id"] == "user123"

    @patch.dict(os.environ, {'BYPASS_AUTH_FOR_TESTS': 'false'})
    @patch('auth_utils.verify_jwt_token')
    def test_auth_required_normal_flow_error(self, mock_verify):
        mock_verify.return_value = (None, 'Invalid token')

        @auth_required
        def test_handler(event, context):
            return {"statusCode": 200}

        event = {'headers': {'Authorization': 'Bearer invalid.token'}}
        result = test_handler(event, {})
        assert result["statusCode"] == 401
        body = json.loads(result["body"])
        assert body["error"] == "Invalid token"
