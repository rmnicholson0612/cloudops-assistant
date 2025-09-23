#!/usr/bin/env python3
"""Test boto3 GA date extraction from AWS docs"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend', 'lambda'))

from eol_tracker import parse_aws_support_matrix

def test_boto3_ga_extraction():
    """Test extracting boto3 GA date from AWS documentation"""
    print("Testing boto3 GA date extraction...")

    # Simulate AWS documentation HTML with boto3 GA date
    mock_aws_html = """
    <html>
    <body>
    <table>
    <tr><td>JavaScript</td><td>2.x</td><td>End-of-Support</td></tr>
    <tr><td>JavaScript</td><td>3.x</td><td>General Availability</td><td>12/15/2020</td></tr>
    <tr><td>Python</td><td>boto3</td><td>General Availability</td><td>6/23/2015</td></tr>
    </table>
    </body>
    </html>
    """

    # Parse the matrix
    sdk_data = parse_aws_support_matrix(mock_aws_html)
    print(f"Parsed SDK data: {sdk_data}")

    # Check if boto2 got the correct EOL date from boto3 GA
    if 'boto2' in sdk_data:
        boto2_eol = sdk_data['boto2']['eol_date']
        print(f"\nboto2 EOL date: {boto2_eol}")
        if '2015-06-23' in boto2_eol:
            print("CORRECT: boto2 EOL date matches boto3 GA date")
        else:
            print("WRONG: boto2 EOL date doesn't match expected boto3 GA date")
    else:
        print("ERROR: boto2 not found in SDK data")

if __name__ == "__main__":
    test_boto3_ga_extraction()
