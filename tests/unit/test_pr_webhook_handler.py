import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'GITHUB_WEBHOOK_SECRET': 'test-webhook-secret',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from pr_webhook_handler import lambda_handler

class TestPrWebhookHandler:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200

    def test_lambda_handler_invalid_method(self):
        event = {"httpMethod": "GET"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 401

    def test_lambda_handler_missing_signature(self):
        event = {
            "httpMethod": "POST",
            "body": json.dumps({"test": "data"})
        }
        response = lambda_handler(event, {})
        assert response["statusCode"] == 401
