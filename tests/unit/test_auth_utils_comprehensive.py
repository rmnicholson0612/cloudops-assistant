
import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

# Set up environment variables
os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from auth_utils import verify_jwt_token, verify_token, auth_required

class TestAuthUtilsComprehensive:
    def test_verify_jwt_token_missing_header(self):
        event = {'headers': {}}
        user_info, error = verify_jwt_token(event)
        assert user_info is None
        assert error == 'Authorization header missing'

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

    @patch('auth_utils.cognito_client')
    def test_verify_jwt_token_success(self, mock_cognito):
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

    @patch('auth_utils.cognito_client')
    def test_verify_token_exception(self, mock_cognito):
        mock_cognito.get_user.side_effect = Exception('Error')
        result = verify_token('invalid.token')
        assert result is None

    def test_auth_required_bypass(self):
        @auth_required
        def test_handler(event, context):
            return {"statusCode": 200, "user_id": event["user_info"]["user_id"]}

        event = {}
        result = test_handler(event, {})
        assert result["statusCode"] == 200
        assert result["user_id"] == "test-user-123"
