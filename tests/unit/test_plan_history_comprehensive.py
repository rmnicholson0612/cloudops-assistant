
import pytest
import json
from unittest.mock import patch, Mock
import sys
import os

os.environ.update({
    'BYPASS_AUTH_FOR_TESTS': 'true',
    'TERRAFORM_PLANS_TABLE': 'test-terraform-plans-table',
    'AWS_REGION': 'us-east-1'
})

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from plan_history import get_cors_headers, error_response, success_response, get_plan_history, get_plan_details, compare_plans

class TestPlanHistoryComprehensive:
    def test_get_cors_headers(self):
        headers = get_cors_headers()
        assert "Access-Control-Allow-Origin" in headers
        assert headers["Access-Control-Allow-Origin"] == "*"

    def test_error_response(self):
        response = error_response(400, "Test error")
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Test error"

    def test_success_response(self):
        data = {"test": "data"}
        response = success_response(data)
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["test"] == "data"

    @patch('plan_history.table')
    def test_get_plan_history_success(self, mock_table):
        mock_table.query.return_value = {
            "Items": [
                {
                    "plan_id": "test-plan",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "changes_detected": 5,
                    "change_summary": ["test change"]
                }
            ]
        }

        response = get_plan_history("test-repo", "user123")
        assert response["statusCode"] == 200

    @patch('plan_history.table')
    def test_get_plan_details_success(self, mock_table):
        mock_table.get_item.return_value = {
            "Item": {
                "plan_id": "test-plan",
                "repo_name": "test-repo",
                "timestamp": "2023-01-01T00:00:00Z",
                "user_id": "user123",
                "changes_detected": 5,
                "plan_content": "test content"
            }
        }

        response = get_plan_details("test-plan", "user123")
        assert response["statusCode"] == 200

    @patch('plan_history.table')
    def test_compare_plans_success(self, mock_table):
        mock_table.get_item.side_effect = [
            {
                "Item": {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "user_id": "user123",
                    "plan_content": "content1\nline2",
                    "changes_detected": 3
                }
            },
            {
                "Item": {
                    "plan_id": "plan2",
                    "timestamp": "2023-01-02T00:00:00Z",
                    "user_id": "user123",
                    "plan_content": "content2\nline2",
                    "changes_detected": 5
                }
            }
        ]

        response = compare_plans("plan1", "plan2", "user123")
        assert response["statusCode"] == 200
