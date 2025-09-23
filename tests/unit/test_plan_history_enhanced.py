"""
Enhanced unit tests for plan_history module - 100% coverage
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal
import sys
import os

# Add backend/lambda to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

from plan_history import (
    lambda_handler, get_plan_history, get_plan_details, compare_plans,
    get_cors_headers, error_response, success_response, DecimalEncoder,
    _authenticated_handler
)


class TestPlanHistoryEnhanced:
    """Enhanced test plan history functionality for 100% coverage"""

    def test_decimal_encoder(self):
        """Test DecimalEncoder handles Decimal objects"""
        encoder = DecimalEncoder()
        assert encoder.default(Decimal('10')) == 10

        # Test non-decimal object raises TypeError
        with pytest.raises(TypeError):
            encoder.default("not a decimal")

    def test_get_cors_headers(self):
        """Test CORS headers are properly formatted"""
        headers = get_cors_headers()
        assert headers["Access-Control-Allow-Origin"] == "*"
        assert "Authorization" in headers["Access-Control-Allow-Headers"]
        assert "GET,POST,PUT,DELETE,OPTIONS" == headers["Access-Control-Allow-Methods"]

    def test_error_response(self):
        """Test error response formatting"""
        response = error_response(400, "Test error")
        assert response["statusCode"] == 400
        assert "Access-Control-Allow-Origin" in response["headers"]
        body = json.loads(response["body"])
        assert body["error"] == "Test error"

    def test_success_response(self):
        """Test success response formatting"""
        data = {"test": "data", "number": Decimal('5')}
        response = success_response(data)
        assert response["statusCode"] == 200
        assert "Access-Control-Allow-Origin" in response["headers"]
        body = json.loads(response["body"])
        assert body["test"] == "data"
        assert body["number"] == 5

    def test_lambda_handler_options(self):
        """Test OPTIONS request handling"""
        event = {"httpMethod": "OPTIONS"}
        response = lambda_handler(event, {})
        assert response["statusCode"] == 200
        assert "Access-Control-Allow-Origin" in response["headers"]

    @patch('plan_history.get_plan_history')
    def test_authenticated_handler_plan_history(self, mock_get_history):
        """Test plan history endpoint"""
        mock_get_history.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/plan-history/test-repo",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 200
        mock_get_history.assert_called_once_with("test-repo", "test-user-123")

    def test_authenticated_handler_plan_history_no_repo(self):
        """Test plan history endpoint without repo name"""
        event = {
            "httpMethod": "GET",
            "path": "/plan-history/",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Repository name required"

    def test_authenticated_handler_plan_history_empty_repo(self):
        """Test plan history endpoint with empty repo name"""
        event = {
            "httpMethod": "GET",
            "path": "/plan-history//",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Repository name required"

    @patch('plan_history.get_plan_details')
    def test_authenticated_handler_plan_details(self, mock_get_details):
        """Test plan details endpoint"""
        mock_get_details.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/plan-details/plan123",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 200
        mock_get_details.assert_called_once_with("plan123", "test-user-123")

    @patch('plan_history.get_plan_details')
    def test_authenticated_handler_plan_details_path_params(self, mock_get_details):
        """Test plan details endpoint with path parameters"""
        mock_get_details.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/plan-details/",
            "pathParameters": {"plan_id": "plan123"},
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 200
        mock_get_details.assert_called_once_with("plan123", "test-user-123")

    def test_authenticated_handler_plan_details_no_id(self):
        """Test plan details endpoint without plan ID"""
        event = {
            "httpMethod": "GET",
            "path": "/plan-details/",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Plan ID required"

    @patch('plan_history.compare_plans')
    def test_authenticated_handler_compare_plans(self, mock_compare):
        """Test compare plans endpoint"""
        mock_compare.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/compare-plans/plan1/plan2",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 200
        mock_compare.assert_called_once_with("plan1", "plan2", "test-user-123")

    @patch('plan_history.compare_plans')
    def test_authenticated_handler_compare_plans_path_params(self, mock_compare):
        """Test compare plans endpoint with path parameters"""
        mock_compare.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/compare-plans/",
            "pathParameters": {"plan1": "plan1", "plan2": "plan2"},
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 200
        mock_compare.assert_called_once_with("plan1", "plan2", "test-user-123")

    def test_authenticated_handler_compare_plans_missing_ids(self):
        """Test compare plans endpoint without plan IDs"""
        event = {
            "httpMethod": "GET",
            "path": "/compare-plans/",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert body["error"] == "Two plan IDs required"

    def test_authenticated_handler_not_found(self):
        """Test 404 for unknown endpoints"""
        event = {
            "httpMethod": "GET",
            "path": "/unknown",
            "user_info": {"user_id": "test-user-123"}
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 404

    def test_authenticated_handler_exception(self):
        """Test exception handling"""
        event = {
            "httpMethod": "GET",
            "path": "/plan-history/test",
            # Missing user_info to trigger exception
        }

        response = _authenticated_handler(event, {})
        assert response["statusCode"] == 500

    @patch('plan_history.table')
    def test_get_plan_history_success(self, mock_table):
        """Test successful plan history retrieval"""
        mock_table.query.return_value = {
            "Items": [
                {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "changes_detected": 5,
                    "change_summary": ["added resource"]
                }
            ]
        }

        response = get_plan_history("test-repo", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["repo_name"] == "test-repo"
        assert len(body["plans"]) == 1
        assert body["plans"][0]["plan_id"] == "plan1"

    @patch('plan_history.table')
    def test_get_plan_history_missing_fields(self, mock_table):
        """Test plan history with missing optional fields"""
        mock_table.query.return_value = {
            "Items": [
                {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z"
                    # Missing changes_detected and change_summary
                }
            ]
        }

        response = get_plan_history("test-repo", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["plans"][0]["changes_detected"] == 0
        assert body["plans"][0]["change_summary"] == []

    @patch('plan_history.table')
    def test_get_plan_history_exception(self, mock_table):
        """Test plan history exception handling"""
        mock_table.query.side_effect = Exception("Database error")

        response = get_plan_history("test-repo", "test-user-123")
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Failed to get history"

    @patch('plan_history.table')
    def test_get_plan_details_success(self, mock_table):
        """Test successful plan details retrieval"""
        mock_table.get_item.return_value = {
            "Item": {
                "plan_id": "plan123",
                "repo_name": "test-repo",
                "timestamp": "2023-01-01T00:00:00Z",
                "user_id": "test-user-123",
                "changes_detected": 3,
                "plan_content": "terraform plan output",
                "change_summary": ["added resource"],
                "ai_explanation": "AI analysis",
                "ai_analyzed_at": "2023-01-01T01:00:00Z",
                "drift_detected": True
            }
        }

        response = get_plan_details("plan123", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["plan_id"] == "plan123"
        assert body["repo_name"] == "test-repo"
        assert body["ai_explanation"] == "AI analysis"
        assert body["drift_detected"] is True

    @patch('plan_history.table')
    def test_get_plan_details_missing_optional_fields(self, mock_table):
        """Test plan details with missing optional fields"""
        mock_table.get_item.return_value = {
            "Item": {
                "plan_id": "plan123",
                "repo_name": "test-repo",
                "timestamp": "2023-01-01T00:00:00Z",
                "user_id": "test-user-123"
                # Missing optional fields
            }
        }

        response = get_plan_details("plan123", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["changes_detected"] == 0
        assert body["drift_detected"] is False
        assert body["plan_content"] == ""
        assert body["change_summary"] == []

    @patch('plan_history.table')
    def test_get_plan_details_not_found(self, mock_table):
        """Test plan details not found"""
        mock_table.get_item.return_value = {}

        response = get_plan_details("plan123", "test-user-123")
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Plan not found"

    @patch('plan_history.table')
    def test_get_plan_details_access_denied(self, mock_table):
        """Test plan details access denied"""
        mock_table.get_item.return_value = {
            "Item": {
                "plan_id": "plan123",
                "user_id": "other_user"
            }
        }

        response = get_plan_details("plan123", "test-user-123")
        assert response["statusCode"] == 403
        body = json.loads(response["body"])
        assert body["error"] == "Access denied"

    def test_get_plan_details_invalid_id(self):
        """Test plan details with invalid ID"""
        response = get_plan_details(123, "test-user-123")  # Non-string ID
        assert response["statusCode"] == 500

    @patch('plan_history.table')
    def test_get_plan_details_exception(self, mock_table):
        """Test plan details exception handling"""
        mock_table.get_item.side_effect = Exception("Database error")

        response = get_plan_details("plan123", "test-user-123")
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Failed to get plan details"

    @patch('plan_history.table')
    def test_compare_plans_success(self, mock_table):
        """Test successful plan comparison"""
        mock_table.get_item.side_effect = [
            {
                "Item": {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "user_id": "test-user-123",
                    "plan_content": "line1\nline2",
                    "changes_detected": 2
                }
            },
            {
                "Item": {
                    "plan_id": "plan2",
                    "timestamp": "2023-01-02T00:00:00Z",
                    "user_id": "test-user-123",
                    "plan_content": "line1\nline3",
                    "changes_detected": 3
                }
            }
        ]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["plan1"]["id"] == "plan1"
        assert body["plan2"]["id"] == "plan2"
        assert "diff" in body

    @patch('plan_history.table')
    def test_compare_plans_missing_plan_content(self, mock_table):
        """Test plan comparison with missing plan content"""
        mock_table.get_item.side_effect = [
            {
                "Item": {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "user_id": "test-user-123"
                    # Missing plan_content
                }
            },
            {
                "Item": {
                    "plan_id": "plan2",
                    "timestamp": "2023-01-02T00:00:00Z",
                    "user_id": "test-user-123"
                    # Missing plan_content
                }
            }
        ]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert "diff" in body

    @patch('plan_history.table')
    def test_compare_plans_first_not_found(self, mock_table):
        """Test compare plans when first plan not found"""
        mock_table.get_item.side_effect = [{}, {"Item": {"user_id": "test-user-123"}}]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "First plan not found"

    @patch('plan_history.table')
    def test_compare_plans_second_not_found(self, mock_table):
        """Test compare plans when second plan not found"""
        mock_table.get_item.side_effect = [{"Item": {"user_id": "test-user-123"}}, {}]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 404
        body = json.loads(response["body"])
        assert body["error"] == "Second plan not found"

    @patch('plan_history.table')
    def test_compare_plans_access_denied_first(self, mock_table):
        """Test compare plans access denied for first plan"""
        mock_table.get_item.side_effect = [
            {"Item": {"user_id": "other_user"}},
            {"Item": {"user_id": "test-user-123"}}
        ]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 403

    @patch('plan_history.table')
    def test_compare_plans_access_denied_second(self, mock_table):
        """Test compare plans access denied for second plan"""
        mock_table.get_item.side_effect = [
            {"Item": {"user_id": "test-user-123"}},
            {"Item": {"user_id": "other_user"}}
        ]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 403

    def test_compare_plans_invalid_ids(self):
        """Test compare plans with invalid IDs"""
        response = compare_plans(123, "plan2", "test-user-123")
        assert response["statusCode"] == 500

    @patch('plan_history.table')
    def test_compare_plans_exception(self, mock_table):
        """Test compare plans exception handling"""
        mock_table.get_item.side_effect = Exception("Database error")

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Failed to compare plans"

    @patch('plan_history.table')
    def test_compare_plans_large_diff(self, mock_table):
        """Test plan comparison with large diff (limited to 100 lines)"""
        # Create large plan content
        large_content1 = "\n".join([f"line{i}" for i in range(200)])
        large_content2 = "\n".join([f"different_line{i}" for i in range(200)])

        mock_table.get_item.side_effect = [
            {
                "Item": {
                    "plan_id": "plan1",
                    "timestamp": "2023-01-01T00:00:00Z",
                    "user_id": "test-user-123",
                    "plan_content": large_content1,
                    "changes_detected": 2
                }
            },
            {
                "Item": {
                    "plan_id": "plan2",
                    "timestamp": "2023-01-02T00:00:00Z",
                    "user_id": "test-user-123",
                    "plan_content": large_content2,
                    "changes_detected": 3
                }
            }
        ]

        response = compare_plans("plan1", "plan2", "test-user-123")
        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert len(body["diff"]) <= 100  # Limited to 100 lines
