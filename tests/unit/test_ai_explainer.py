
import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from ai_explainer import lambda_handler

class TestAIExplainer:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200

    @patch.dict(os.environ, {'BYPASS_AUTH_FOR_TESTS': 'true'})
    def test_lambda_handler_invalid_path(self):
        event = {
            "httpMethod": "POST",
            "path": "/invalid",
            "body": json.dumps({"plan_id": "test-plan"}),
            "user_info": {"user_id": "test-user-123"}
        }
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404
