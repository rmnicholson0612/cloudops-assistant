"""
Test EOL mapping and API functionality
"""

import pytest
import requests
import sys
import os
from unittest.mock import patch, Mock

# Add backend/lambda to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'backend', 'lambda'))

# Mock boto3 before importing modules that use it
with patch('boto3.client'), patch('boto3.resource'):
    from eol_tracker import map_to_eol_api_name, fetch_from_endoflife_api


class TestEOLMapping:
    """Test EOL mapping functionality"""

    def test_aws_sdk_scoped_packages_mapping(self):
        """Test @aws-sdk/ scoped packages map to aws-sdk"""
        assert map_to_eol_api_name('@aws-sdk/client-s3') == 'aws-sdk'
        assert map_to_eol_api_name('@aws-sdk/client-lambda') == 'aws-sdk'
        assert map_to_eol_api_name('@aws-sdk/client-dynamodb') == 'aws-sdk'

    def test_aws_sdk_packages_mapping(self):
        """Test AWS SDK packages map to correct APIs"""
        assert map_to_eol_api_name('boto3') == 'python'
        assert map_to_eol_api_name('aws-sdk') == 'aws-sdk'
        assert map_to_eol_api_name('aws-cdk') == 'aws-sdk'

    def test_nodejs_packages_mapping(self):
        """Test Node.js packages map to node"""
        assert map_to_eol_api_name('axios') == 'node'
        assert map_to_eol_api_name('lodash') == 'node'
        assert map_to_eol_api_name('express') == 'express'

    def test_language_mapping(self):
        """Test language mappings"""
        assert map_to_eol_api_name('nodejs') == 'node'
        assert map_to_eol_api_name('python') == 'python'
        assert map_to_eol_api_name('java') == 'java'


class TestEOLAPIIntegration:
    """Test actual EOL API calls"""

    def test_node_api_endpoint_exists(self):
        """Test that the Node.js EOL API endpoint actually works"""
        try:
            response = requests.get('https://endoflife.date/api/node.json', timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
            # Check that we have actual Node.js versions
            assert any('18' in str(item.get('cycle', '')) for item in data)
        except requests.RequestException:
            pytest.skip("EOL API not accessible")

    def test_python_api_endpoint_exists(self):
        """Test that the Python EOL API endpoint works"""
        try:
            response = requests.get('https://endoflife.date/api/python.json', timeout=10)
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) > 0
        except requests.RequestException:
            pytest.skip("EOL API not accessible")

    def test_fetch_from_endoflife_api_node(self):
        """Test fetching Node.js EOL data"""
        result = fetch_from_endoflife_api('node', '18')
        if result:  # Only test if API is accessible
            assert 'eol_date' in result
            assert 'risk_level' in result
            assert result['eol_date'] is not None
            # Ensure it's not a 1969 date
            assert '1969' not in result['eol_date']

    def test_fetch_from_endoflife_api_python(self):
        """Test fetching Python EOL data"""
        result = fetch_from_endoflife_api('python', '3.9')
        if result:  # Only test if API is accessible
            assert 'eol_date' in result
            assert 'risk_level' in result
            assert result['eol_date'] is not None
            # Ensure it's not a 1969 date
            assert '1969' not in result['eol_date']

    def test_nonexistent_api_returns_none(self):
        """Test that non-existent APIs return None"""
        result = fetch_from_endoflife_api('nonexistent-api', '1.0')
        assert result is None


if __name__ == '__main__':
    # Quick manual test
    print("Testing AWS SDK mappings:")
    print(f"@aws-sdk/client-s3 -> {map_to_eol_api_name('@aws-sdk/client-s3')}")
    print(f"boto3 -> {map_to_eol_api_name('boto3')}")
    print(f"axios -> {map_to_eol_api_name('axios')}")

    print("\nTesting Node.js API:")
    result = fetch_from_endoflife_api('node', '18')
    if result:
        print(f"Node.js 18 EOL: {result['eol_date']} (risk: {result['risk_level']})")
    else:
        print("No Node.js EOL data found")
