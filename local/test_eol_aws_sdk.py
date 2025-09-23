#!/usr/bin/env python3
"""Test AWS SDK EOL logic"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend', 'lambda'))

from eol_tracker import fetch_from_aws_sdk_api, parse_aws_support_matrix, get_aws_sdk_eol_from_matrix

def test_aws_sdk_eol():
    """Test AWS SDK EOL detection"""
    print("Testing AWS SDK EOL logic...")

    # Test data simulating AWS support matrix
    mock_html = """
    <html>
    <body>
    <table>
    <tr><td>JavaScript</td><td>2.x</td><td>End-of-Support</td></tr>
    <tr><td>JavaScript</td><td>3.x</td><td>General Availability</td><td>12/15/2020</td></tr>
    </table>
    </body>
    </html>
    """

    # Parse the matrix
    sdk_data = parse_aws_support_matrix(mock_html)
    print(f"Parsed SDK data: {sdk_data}")

    # Test different AWS SDK packages
    test_cases = [
        ("aws-sdk", "2.1.0"),  # v2 SDK
        ("@aws-sdk/client-s3", "3.0.0"),  # v3 scoped package
        ("aws-sdk", None),  # No version specified
        ("boto3", "1.26.0"),  # Python SDK
    ]

    for api_name, version in test_cases:
        print(f"\nTesting {api_name} version {version}:")
        result = get_aws_sdk_eol_from_matrix(api_name, version, sdk_data)
        if result:
            print(f"  EOL Date: {result.get('eol_date')}")
            print(f"  Risk Level: {result.get('risk_level')}")
            print(f"  Status: {result.get('status')}")
            print(f"  Successor: {result.get('successor_version')}")
        else:
            print("  No EOL data found")

if __name__ == "__main__":
    test_aws_sdk_eol()
