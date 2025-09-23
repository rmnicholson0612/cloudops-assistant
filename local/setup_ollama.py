#!/usr/bin/env python3
"""
Setup Ollama for local AI development
"""

import subprocess
import requests
import time

def setup_ollama():
    """Setup Ollama with appropriate model for CloudOps"""

    print("Setting up Ollama for local AI development...")

    # Check if Ollama is running
    try:
        response = requests.get("http://localhost:11434/api/tags")
        print("✅ Ollama is running")
    except:
        print("❌ Ollama not running. Please install and start Ollama:")
        print("1. Download from: https://ollama.ai/download")
        print("2. Run: ollama serve")
        return False

    # Pull recommended model for code analysis
    models_to_try = [
        "gemma3:270m"
    ]

    for model in models_to_try:
        try:
            print(f"Pulling {model}...")
            subprocess.run(["ollama", "pull", model], check=True)
            print(f"✅ {model} ready")
            return model
        except:
            print(f"❌ Failed to pull {model}")
            continue

    return None

if __name__ == "__main__":
    model = setup_ollama()
    if model:
        print(f"🚀 Ready to use {model} for local AI features")
    else:
        print("❌ Setup failed")
