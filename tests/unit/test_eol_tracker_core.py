"""
Unit tests for EOL tracker core functionality
"""

import pytest
from unittest.mock import patch, Mock
from datetime import datetime, timezone
import sys
import os

# Add backend/lambda to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

# Mock boto3 before importing
with patch('boto3.client'), patch('boto3.resource'):
    from eol_tracker import calculate_risk_level, catalog_and_check_eol, parse_dependency_file


class TestEOLRiskCalculation:
    """Test EOL risk calculation logic"""

    def test_calculate_risk_level_critical(self):
        """Test critical risk for past EOL date"""
        past_date = "2020-01-01T00:00:00Z"
        assert calculate_risk_level(past_date) == "critical"

    def test_calculate_risk_level_high(self):
        """Test high risk for EOL within 3 months"""
        # 30 days from now
        future_date = datetime.now(timezone.utc).replace(day=1)
        future_date = future_date.replace(month=future_date.month + 1)
        date_str = future_date.isoformat().replace('+00:00', 'Z')

        assert calculate_risk_level(date_str) == "high"

    def test_calculate_risk_level_medium(self):
        """Test medium risk for EOL within 1 year"""
        # 6 months from now
        from datetime import timedelta
        future_date = datetime.now(timezone.utc) + timedelta(days=180)
        date_str = future_date.isoformat().replace('+00:00', 'Z')

        assert calculate_risk_level(date_str) == "medium"

    def test_calculate_risk_level_low(self):
        """Test low risk for EOL more than 1 year away"""
        # 2 years from now
        future_date = datetime.now(timezone.utc).replace(year=datetime.now().year + 2)
        date_str = future_date.isoformat().replace('+00:00', 'Z')

        assert calculate_risk_level(date_str) == "low"

    def test_calculate_risk_level_unknown(self):
        """Test unknown risk for invalid dates"""
        assert calculate_risk_level(False) == "unknown"
        assert calculate_risk_level("invalid-date") == "unknown"
        assert calculate_risk_level(None) == "unknown"


class TestDependencyParsing:
    """Test dependency file parsing"""

    def test_parse_requirements_txt(self):
        """Test parsing Python requirements.txt"""
        content = """
requests==2.28.1
flask>=2.0.0
boto3
# This is a comment
django==4.1.0
"""

        with patch('eol_tracker.catalog_and_check_eol') as mock_catalog:
            mock_catalog.return_value = {'technology': 'requests', 'version': '2.28.1'}

            findings = parse_dependency_file('requirements.txt', content, {'name': 'test-repo'}, 'requirements.txt')

            # Should find 4 packages (excluding comment)
            assert len(findings) == 4
            assert mock_catalog.call_count == 4

    def test_parse_package_json(self):
        """Test parsing Node.js package.json"""
        content = """{
  "name": "test-app",
  "engines": {
    "node": "18.0.0"
  },
  "dependencies": {
    "express": "^4.18.0",
    "lodash": "4.17.21"
  },
  "devDependencies": {
    "jest": "^29.0.0"
  }
}"""

        with patch('eol_tracker.catalog_and_check_eol') as mock_catalog:
            mock_catalog.return_value = {'technology': 'nodejs', 'version': '18.0.0'}

            findings = parse_dependency_file('package.json', content, {'name': 'test-repo'}, 'package.json')

            # Should find Node.js version + 3 packages
            assert len(findings) == 4
            assert mock_catalog.call_count == 4

    def test_parse_dockerfile(self):
        """Test parsing Dockerfile"""
        content = """
FROM python:3.9-slim
FROM node:18-alpine
COPY . /app
RUN pip install -r requirements.txt
"""

        with patch('eol_tracker.catalog_and_check_eol') as mock_catalog:
            mock_catalog.return_value = {'technology': 'python', 'version': '3.9'}

            findings = parse_dependency_file('Dockerfile', content, {'name': 'test-repo'}, 'Dockerfile')

            # Should find Python and Node.js base images
            assert len(findings) == 2
            assert mock_catalog.call_count == 2


class TestCatalogAndCheckEOL:
    """Test technology cataloging and EOL checking"""

    @patch('eol_tracker.eol_database_table')
    def test_catalog_with_cached_eol_data(self, mock_table):
        """Test cataloging with existing EOL data in cache"""
        # Mock DynamoDB response with cached EOL data
        mock_table.get_item.return_value = {
            'Item': {
                'eol_date': '2025-12-31T00:00:00Z',
                'risk_level': 'low'
            }
        }

        result = catalog_and_check_eol('language', 'python', '3.9', 'test-repo')

        assert result['technology'] == 'python'
        assert result['version'] == '3.9'
        assert result['eol_date'] == '2025-12-31T00:00:00Z'
        # Risk level is calculated from eol_date, not cached
        assert result['risk_level'] == 'medium'  # 2025-12-31 is medium risk

    @patch('eol_tracker.eol_database_table')
    @patch('eol_tracker.fetch_from_eol_api')
    def test_catalog_with_api_fetch(self, mock_fetch, mock_table):
        """Test cataloging with API fetch when no cache"""
        # Mock no cached data
        mock_table.get_item.return_value = {}

        # Mock API response
        mock_fetch.return_value = {
            'eol_date': '2024-10-01T00:00:00Z',
            'risk_level': 'high'
        }

        with patch('eol_tracker.map_to_eol_api_name') as mock_map:
            mock_map.return_value = 'python'

            result = catalog_and_check_eol('language', 'python', '3.8', 'test-repo')

            assert result['eol_date'] == '2024-10-01T00:00:00Z'
            assert result['risk_level'] == 'high'
            mock_fetch.assert_called_once_with('python', '3.8')

    @patch('eol_tracker.eol_database_table')
    def test_catalog_error_handling(self, mock_table):
        """Test error handling in cataloging"""
        # Mock database error
        mock_table.get_item.side_effect = Exception("Database error")

        result = catalog_and_check_eol('language', 'python', '3.9', 'test-repo')

        assert result['technology'] == 'python'
        assert result['risk_level'] == 'error'
        assert 'error' in result
