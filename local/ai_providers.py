#!/usr/bin/env python3
"""
AI providers for local development
"""

import os
import json
import requests
from typing import Dict, Any, Optional

class OllamaProvider:
    """Local Ollama AI provider"""

    def __init__(self, model: str = "gemma3:270m", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url

    def invoke_model(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Invoke Ollama model"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.1
                    }
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return {
                    "body": json.dumps({
                        "content": [{"text": result.get("response", "")}]
                    })
                }
            else:
                raise Exception(f"Ollama API error: {response.status_code}")

        except Exception as e:
            print(f"Ollama error: {e}")
            return self._fallback_response(prompt)

    def _fallback_response(self, prompt: str) -> Dict[str, Any]:
        """Fallback when Ollama fails"""
        return {
            "body": json.dumps({
                "content": [{"text": "AI analysis unavailable in local mode. Please start Ollama or use OpenAI provider."}]
            })
        }

class OpenAIProvider:
    """OpenAI API provider for local development"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = "https://api.openai.com/v1"

    def invoke_model(self, prompt: str, max_tokens: int = 2000) -> Dict[str, Any]:
        """Invoke OpenAI model"""
        if not self.api_key:
            return self._no_key_response()

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.1
                },
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                return {
                    "body": json.dumps({
                        "content": [{"text": content}]
                    })
                }
            else:
                raise Exception(f"OpenAI API error: {response.status_code}")

        except Exception as e:
            print(f"OpenAI error: {e}")
            return self._error_response(str(e))

    def _no_key_response(self) -> Dict[str, Any]:
        return {
            "body": json.dumps({
                "content": [{"text": "OpenAI API key not configured. Set OPENAI_API_KEY environment variable."}]
            })
        }

    def _error_response(self, error: str) -> Dict[str, Any]:
        return {
            "body": json.dumps({
                "content": [{"text": f"OpenAI API error: {error}"}]
            })
        }

def get_ai_provider() -> Any:
    """Get the best available AI provider"""

    # Try Ollama first (free)
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        if response.status_code == 200:
            print("Using Ollama for local AI")
            return OllamaProvider()
    except requests.RequestException as e:
        import logging
        logging.warning(f"Ollama connection failed: {e}")

    # Fall back to OpenAI if available
    if os.getenv("OPENAI_API_KEY"):
        print("Using OpenAI for local AI")
        return OpenAIProvider()

    # Return Ollama with fallback
    print("No AI provider available - using fallback responses")
    return OllamaProvider()
