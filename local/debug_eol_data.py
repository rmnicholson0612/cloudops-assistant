#!/usr/bin/env python3
"""
Debug EOL data to see what's actually stored in DynamoDB
"""
import boto3
import json
from pprint import pprint

def debug_eol_data():
    """Debug what's actually in the EOL tables"""
    try:
        # Connect to LocalStack
        dynamodb = boto3.resource('dynamodb', endpoint_url='http://localhost:4566', region_name='us-east-1')

        # Check EOL scans table
        scans_table = dynamodb.Table('cloudops-assistant-eol-scans')

        print("=== EOL SCANS TABLE ===")
        response = scans_table.scan()
        items = response.get('Items', [])

        print(f"Found {len(items)} scan records")

        for i, item in enumerate(items):
            print(f"\n--- Scan {i+1} ---")
            print(f"Scan ID: {item.get('scan_id')}")
            print(f"Repo: {item.get('repo_name')}")
            print(f"Scan Date: {item.get('scan_date')}")

            findings = item.get('findings', [])
            print(f"Findings: {len(findings)}")

            for j, finding in enumerate(findings[:3]):  # Show first 3 findings
                print(f"\n  Finding {j+1}:")
                print(f"    Technology: {finding.get('technology')}")
                print(f"    Version: {finding.get('version')}")
                print(f"    Tech Type: {finding.get('tech_type')}")
                print(f"    File Path: {finding.get('file_path')}")
                print(f"    Line Number: {finding.get('line_number')}")
                print(f"    GitHub URL: {finding.get('github_url')}")
                print(f"    Source: {finding.get('source')}")
                print(f"    Risk Level: {finding.get('risk_level')}")
                print(f"    Last Seen: {finding.get('last_seen')}")

        # Test the frontend data flow
        print("\n=== TESTING FRONTEND DATA FLOW ===")

        # Simulate what the frontend gets
        all_findings = []
        for scan in items:
            findings = scan.get('findings', [])
            for finding in findings:
                all_findings.append({
                    **finding,
                    'repo_name': scan.get('repo_name'),
                    'scan_date': scan.get('scan_date')
                })

        print(f"Total flattened findings: {len(all_findings)}")

        if all_findings:
            print("\nFirst finding as frontend would see it:")
            first_finding = all_findings[0]
            pprint(first_finding)

            print(f"\nSource field check:")
            print(f"  source: {first_finding.get('source')}")
            print(f"  github_url: {first_finding.get('github_url')}")
            print(f"  file_path: {first_finding.get('file_path')}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_eol_data()
