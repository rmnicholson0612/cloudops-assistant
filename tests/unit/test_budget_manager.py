import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'BUDGETS_TABLE': 'test-budgets-table',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from budget_manager import lambda_handler

class TestBudgetManager:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200

    def test_lambda_handler_invalid_method(self):
        event = {"httpMethod": "PATCH", "user_info": {"user_id": "test-user"}}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 401

    def test_lambda_handler_invalid_json(self):
        event = {
            "httpMethod": "POST",
            "body": "invalid json",
            "user_info": {"user_id": "test-user"}
        }
        response = lambda_handler(event, {})
        assert response["statusCode"] == 401
