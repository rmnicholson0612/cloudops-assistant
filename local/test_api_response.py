#!/usr/bin/env python3
"""
Test what the API is actually returning to the frontend
"""
import requests
import json
from pprint import pprint

def test_api_response():
    """Test the actual API response"""
    try:
        # Test the EOL scans endpoint (what frontend calls)
        url = "http://localhost:3001/eol/scans"

        print("=== TESTING API RESPONSE ===")
        print(f"Calling: {url}")

        response = requests.get(url, timeout=10)
        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"Response keys: {data.keys()}")

            scans = data.get('scans', [])
            print(f"Number of scans: {len(scans)}")

            if scans:
                first_scan = scans[0]
                print(f"\nFirst scan keys: {first_scan.keys()}")
                print(f"Repo: {first_scan.get('repo_name')}")

                findings = first_scan.get('findings', [])
                print(f"Findings count: {len(findings)}")

                if findings:
                    print(f"\nFirst finding:")
                    first_finding = findings[0]
                    pprint(first_finding)

                    print(f"\nKey fields:")
                    print(f"  source: {first_finding.get('source')}")
                    print(f"  github_url: {first_finding.get('github_url')}")
                    print(f"  file_path: {first_finding.get('file_path')}")
                    print(f"  line_number: {first_finding.get('line_number')}")
        else:
            print(f"Error: {response.text}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api_response()
