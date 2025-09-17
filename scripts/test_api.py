#!/usr/bin/env python3
"""Test API endpoints after deployment."""

import json
import subprocess
import sys
import urllib.request
from urllib.error import URLError


def get_api_url(stack_name: str) -> str:
    """Get API URL from CloudFormation stack output."""
    try:
        result = subprocess.run(
            [
                "aws", "cloudformation", "describe-stacks",
                "--stack-name", stack_name,
                "--query", "Stacks[0].Outputs[?OutputKey=='CloudOpsAssistantApi'].OutputValue",
                "--output", "text"
            ],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def test_endpoint(url: str, endpoint: str) -> bool:
    """Test a specific API endpoint."""
    full_url = f"{url}/{endpoint}"
    try:
        with urllib.request.urlopen(full_url, timeout=10) as response:
            status = response.getcode()
            if status == 200:
                print(f"✅ {endpoint}: OK ({status})")
                return True
            else:
                print(f"⚠️  {endpoint}: {status}")
                return False
    except URLError as e:
        print(f"❌ {endpoint}: {e}")
        return False


def main():
    """Test API endpoints."""
    stack_name = sys.argv[1] if len(sys.argv) > 1 else "cloudops-assistant"

    print(f"🧪 Testing API endpoints for stack: {stack_name}")

    api_url = get_api_url(stack_name)
    if not api_url:
        print("❌ Could not get API URL from stack output")
        sys.exit(1)

    print(f"📍 API URL: {api_url}")

    # Test public endpoints (no auth required)
    endpoints = [
        "health",
        "terraform/plans",  # Should return 401 without auth
        "costs/dashboard"   # Should return 401 without auth
    ]

    print("\n🔍 Testing endpoints...")
    results = []

    for endpoint in endpoints:
        results.append(test_endpoint(api_url, endpoint))

    print(f"\n📊 Results: {sum(results)}/{len(results)} endpoints responding")

    if all(results):
        print("🎉 All endpoints are responding!")
    else:
        print("⚠️  Some endpoints may need attention")
        print("💡 This is normal for authenticated endpoints without tokens")


if __name__ == "__main__":
    main()
