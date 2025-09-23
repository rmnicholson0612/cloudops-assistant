#!/usr/bin/env python3
"""
Test script for local AI integration
"""

import requests
import json
import time

def test_ollama_direct():
    """Test Ollama directly"""
    print("Testing Ollama direct connection...")
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"Ollama running with {len(models)} models")
            for model in models:
                print(f"   - {model['name']}")
            return True
        else:
            print(f"Ollama API error: {response.status_code}")
            return False
    except Exception as e:
        print(f"Ollama connection failed: {e}")
        return False

def test_ai_provider():
    """Test AI provider wrapper"""
    print("\nTesting AI provider wrapper...")
    try:
        from ai_providers import get_ai_provider
        ai = get_ai_provider()

        response = ai.invoke_model("What is Terraform?", max_tokens=50)
        body = json.loads(response['body'])
        text = body['content'][0]['text']

        if text and len(text) > 10:
            print(f"AI provider working")
            print(f"   Response: {text[:100]}...")
            return True
        else:
            print("AI provider returned empty response")
            return False

    except Exception as e:
        print(f"AI provider error: {e}")
        return False

def test_local_server_ai():
    """Test AI through local server"""
    print("\nTesting AI through local server...")
    try:
        # Test AI explain endpoint
        response = requests.post(
            "http://localhost:8080/ai/explain",
            json={
                "plan_content": "resource \"aws_instance\" \"example\" {\n  instance_type = \"t3.micro\"\n}"
            },
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            if 'explanations' in data and data['explanations']:
                print("Local server AI endpoint working")
                print(f"   AI Provider: {data.get('ai_provider', 'unknown')}")
                return True

        print(f"Local server AI failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

    except Exception as e:
        print(f"Local server AI error: {e}")
        return False

def main():
    print("CloudOps Assistant AI Integration Test")
    print("=" * 40)

    tests = [
        test_ollama_direct,
        test_ai_provider,
        test_local_server_ai
    ]

    results = []
    for test in tests:
        results.append(test())
        time.sleep(1)

    print("\n" + "=" * 40)
    print(f"Results: {sum(results)}/{len(results)} tests passed")

    if all(results):
        print("All AI integration tests passed!")
    else:
        print("Some tests failed. Check the output above.")
        print("\nTroubleshooting:")
        print("1. Make sure Docker Compose is running: docker-compose up -d")
        print("2. Run setup script: python setup_local_ai.py")
        print("3. Start local server: python local_server.py")

if __name__ == "__main__":
    main()
