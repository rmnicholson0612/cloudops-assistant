import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'SLACK_LINKING_TABLE': 'test-slack-linking-table',
    'SLACK_CLIENT_ID': 'test-client-id',
    'SLACK_CLIENT_SECRET': 'test-client-secret',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from slack_linking import lambda_handler

class TestSlackLinking:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404

    def test_lambda_handler_invalid_method(self):
        event = {"httpMethod": "POST", "user_info": {"user_id": "test-user"}}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404

    def test_lambda_handler_missing_params(self):
        event = {
            "httpMethod": "GET",
            "user_info": {"user_id": "test-user"}
        }
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404
