#!/usr/bin/env python3
"""Test AWS SDK v3 EOL logic specifically"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend', 'lambda'))

from eol_tracker import get_aws_sdk_eol_from_matrix, parse_aws_support_matrix

def test_aws_sdk_v3():
    """Test AWS SDK v3 specifically"""
    print("Testing AWS SDK v3 EOL logic...")

    sdk_data = {
        'aws-sdk-v2': {
            'status': 'End-of-Support',
            'eol_date': '2020-12-15T00:00:00Z',
            'risk_level': 'critical',
            'successor_version': '3.x'
        },
        'aws-sdk-v3': {
            'status': 'General Availability',
            'eol_date': None,
            'risk_level': 'low'
        }
    }

    # Test v3 cases that should NOT have EOL dates
    test_cases = [
        ("aws-sdk", "3.0.0"),
        ("aws-sdk", "3.1.5"),
        ("@aws-sdk/client-s3", "3.0.0"),
        ("@aws-sdk/client-ec2", "3.2.1"),
    ]

    for api_name, version in test_cases:
        print(f"\nTesting {api_name} version {version}:")
        result = get_aws_sdk_eol_from_matrix(api_name, version, sdk_data)
        if result:
            print(f"  WRONG: Found EOL data when shouldn't have")
            print(f"     EOL Date: {result.get('eol_date')}")
            print(f"     Risk Level: {result.get('risk_level')}")
        else:
            print(f"  CORRECT: No EOL data (current version)")

if __name__ == "__main__":
    test_aws_sdk_v3()
