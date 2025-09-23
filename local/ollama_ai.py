#!/usr/bin/env python3
"""
Ollama AI provider for local development
"""

import json
import requests

class OllamaAI:
    def __init__(self, model="gemma3:270m"):
        self.model = model
        self.base_url = "http://localhost:11434"

    def invoke_model(self, prompt, max_tokens=2000):
        """Invoke Ollama model - mimics AWS Bedrock response format"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"num_predict": max_tokens, "temperature": 0.1}
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
                return self._error_response("Ollama request failed")

        except Exception as e:
            return self._error_response(f"Ollama error: {str(e)}")

    def _error_response(self, error):
        return {
            "body": json.dumps({
                "content": [{"text": f"AI unavailable: {error}. Install Ollama and run 'ollama pull '"}]
            })
        }

# Global instance
ollama = OllamaAI()
