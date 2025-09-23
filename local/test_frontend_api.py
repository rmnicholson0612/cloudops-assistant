#!/usr/bin/env python3
"""
Test what the frontend API endpoint returns
"""
import requests
import json

def test_frontend_api():
    """Test the /eol/scans endpoint that frontend calls"""
    try:
        # This is what the frontend calls
        url = "http://localhost:8080/eol/scans"

        # Add mock auth header (since we're bypassing auth in local)
        headers = {
            'Authorization': 'Bearer mock-token',
            'Content-Type': 'application/json'
        }

        print(f"Testing: {url}")
        response = requests.get(url, headers=headers, timeout=10)

        print(f"Status: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            scans = data.get('scans', [])
            print(f"Found {len(scans)} scans")

            if scans:
                # Get first scan with findings
                for scan in scans:
                    findings = scan.get('findings', [])
                    if findings:
                        print(f"\nScan: {scan.get('repo_name')}")
                        print(f"Findings: {len(findings)}")

                        first_finding = findings[0]
                        print(f"\nFirst finding:")
                        print(f"  Technology: {first_finding.get('technology')}")
                        print(f"  Source: {first_finding.get('source')}")
                        print(f"  GitHub URL: {first_finding.get('github_url')}")
                        print(f"  File Path: {first_finding.get('file_path')}")
                        print(f"  Line Number: {first_finding.get('line_number')}")
                        break
        else:
            print(f"Error: {response.text}")

    except requests.exceptions.ConnectionError:
        print("Connection refused - local server not running")
        print("The data is in DynamoDB but the local API server isn't running")
        print("This means you're probably using the deployed version, not local")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_frontend_api()
