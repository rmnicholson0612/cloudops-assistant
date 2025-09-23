"""
Unit tests for cost_analyzer module
"""

import pytest
import json
from unittest.mock import patch, Mock
from datetime import datetime, timedelta
import sys
import os

# Add backend/lambda to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

# Mock boto3 before importing
with patch('boto3.client'), patch('boto3.resource'):
    from cost_analyzer import get_current_costs, get_service_costs, get_cost_trends


class TestCostAnalyzer:
    """Test cost analysis functionality"""

    @patch('cost_analyzer.ce_client')
    @patch('cost_analyzer.get_from_cache')
    def test_get_current_costs_success(self, mock_cache, mock_ce):
        """Test successful current costs retrieval"""
        # Mock no cache
        mock_cache.return_value = None

        # Mock Cost Explorer response
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'Total': {'BlendedCost': {'Amount': '125.50'}}
                }
            ]
        }

        with patch('cost_analyzer.cache_result'):
            result = get_current_costs()

            assert result['statusCode'] == 200
            body = json.loads(result['body'])
            assert body['total_cost'] == 125.50
            assert body['currency'] == 'USD'

    @patch('cost_analyzer.ce_client')
    @patch('cost_analyzer.get_from_cache')
    def test_get_service_costs_success(self, mock_cache, mock_ce):
        """Test successful service costs retrieval"""
        # Mock no cache
        mock_cache.return_value = None

        # Mock Cost Explorer response
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'Groups': [
                        {
                            'Keys': ['EC2-Instance'],
                            'Metrics': {'BlendedCost': {'Amount': '75.25'}}
                        },
                        {
                            'Keys': ['S3'],
                            'Metrics': {'BlendedCost': {'Amount': '25.10'}}
                        }
                    ]
                }
            ]
        }

        with patch('cost_analyzer.cache_result'):
            result = get_service_costs()

            assert result['statusCode'] == 200
            body = json.loads(result['body'])
            assert len(body['services']) == 2
            assert body['services'][0]['service'] == 'EC2-Instance'
            assert body['services'][0]['cost'] == 75.25

    @patch('cost_analyzer.ce_client')
    @patch('cost_analyzer.get_from_cache')
    def test_get_cost_trends_success(self, mock_cache, mock_ce):
        """Test successful cost trends retrieval"""
        # Mock no cache
        mock_cache.return_value = None

        # Mock Cost Explorer response
        mock_ce.get_cost_and_usage.return_value = {
            'ResultsByTime': [
                {
                    'TimePeriod': {'Start': '2024-01-01'},
                    'Total': {'BlendedCost': {'Amount': '10.50'}}
                },
                {
                    'TimePeriod': {'Start': '2024-01-02'},
                    'Total': {'BlendedCost': {'Amount': '12.75'}}
                }
            ]
        }

        with patch('cost_analyzer.cache_result'):
            result = get_cost_trends()

            assert result['statusCode'] == 200
            body = json.loads(result['body'])
            assert len(body['daily_costs']) == 2
            assert body['daily_costs'][0]['cost'] == 10.50
            assert body['daily_costs'][1]['cost'] == 12.75

    @patch('cost_analyzer.get_from_cache')
    def test_cached_response(self, mock_cache):
        """Test cached response handling"""
        # Mock cached data
        cached_data = {
            'total_cost': 100.00,
            'currency': 'USD',
            'period': '2024-01-01 to 2024-01-31'
        }
        mock_cache.return_value = cached_data

        result = get_current_costs()

        assert result['statusCode'] == 200
        body = json.loads(result['body'])
        assert body['total_cost'] == 100.00
