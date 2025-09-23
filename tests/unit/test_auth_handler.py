import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

# Set up environment variables for tests
os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'PR_REVIEWS_TABLE': 'test-pr-reviews-table',
    'TERRAFORM_PLANS_TABLE': 'test-terraform-plans-table',
    'DRIFT_CONFIG_TABLE': 'test-drift-config-table',
    'EOL_DATABASE_TABLE': 'test-eol-database-table',
    'BUDGET_TABLE': 'test-budget-table',
    'COST_CACHE_TABLE': 'test-cost-cache-table',
    'SERVICE_DOCS_TABLE': 'test-service-docs-table',
    'POSTMORTEM_TABLE': 'test-postmortem-table',
    'RESOURCE_DISCOVERY_TABLE': 'test-resource-discovery-table',
    'SLACK_LINKING_TABLE': 'test-slack-linking-table',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from auth_handler import lambda_handler

class TestAuthHandler:
    def test_lambda_handler_options(self):
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200

    def test_lambda_handler_invalid_path(self):
        event = {"httpMethod": "POST", "path": "/invalid"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404

    def test_lambda_handler_invalid_json(self):
        event = {
            "httpMethod": "POST",
            "path": "/register",
            "body": "invalid json"
        }
        response = lambda_handler(event, {})
        assert response["statusCode"] == 404
