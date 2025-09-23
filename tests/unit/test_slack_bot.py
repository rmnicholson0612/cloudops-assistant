import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'SLACK_LINKING_TABLE': 'test-slack-linking-table',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from slack_bot import lambda_handler

class TestSlackBot:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404

    def test_lambda_handler_invalid_method(self):
        event = {"httpMethod": "GET"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404

    def test_lambda_handler_empty_body(self):
        event = {"httpMethod": "POST"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200
