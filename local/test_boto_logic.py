#!/usr/bin/env python3
"""Test boto2/boto3/boto4 succession logic"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend', 'lambda'))

from eol_tracker import get_aws_sdk_eol_from_matrix, parse_aws_support_matrix

def test_boto_succession():
    """Test boto succession logic"""
    print("Testing boto succession logic...")

    # Simulate current state (no boto4 yet)
    sdk_data = {
        'boto2': {
            'status': 'End-of-Support',
            'eol_date': '2015-06-23T00:00:00Z',
            'risk_level': 'critical',
            'successor_version': 'boto3'
        },
        'boto3': {
            'status': 'General Availability',
            'eol_date': None,
            'risk_level': 'low',
            'successor_check': 'boto4'
        },
        'botocore': {
            'status': 'General Availability',
            'eol_date': None,
            'risk_level': 'low',
            'successor_check': None
        }
        # boto4 doesn't exist yet
    }

    test_cases = [
        ("boto2", "2.49.0"),  # Should show EOL
        ("boto3", "1.26.0"),  # Should show no EOL (no boto4 yet)
        ("botocore", "1.29.0"),  # Should show no EOL (maps to boto3)
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
            print(f"  No EOL data (current version)")

    print("\n" + "="*50)
    print("Testing future scenario with boto4...")

    # Simulate future state (boto4 exists)
    sdk_data_future = {
        'boto2': {
            'status': 'End-of-Support',
            'eol_date': '2015-06-23T00:00:00Z',
            'risk_level': 'critical',
            'successor_version': 'boto3'
        },
        'boto3': {
            'status': 'General Availability',
            'eol_date': None,
            'risk_level': 'low',
            'successor_check': 'boto4'
        },
        'boto4': {  # Future version
            'status': 'General Availability',
            'ga_date': '2025-01-01T00:00:00Z',
            'eol_date': None,
            'risk_level': 'low'
        }
    }

    result = get_aws_sdk_eol_from_matrix("boto3", "1.26.0", sdk_data_future)
    if result:
        print(f"\nboto3 with boto4 available:")
        print(f"  EOL Date: {result.get('eol_date')} (should be boto4 GA date)")
        print(f"  Risk Level: {result.get('risk_level')}")
        print(f"  Status: {result.get('status')}")
    else:
        print(f"\nboto3 with boto4 available: No EOL data")

if __name__ == "__main__":
    test_boto_succession()
