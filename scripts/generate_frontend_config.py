#!/usr/bin/env python3
"""Generate frontend configuration from environment variables and stack output."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def get_stack_output(stack_name: str) -> str:
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
        api_url = result.stdout.strip()
        if api_url and api_url != "None":
            print(f"[OK] Found API URL: {api_url}")
            return api_url
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    print("[WARN] Could not get API URL from stack. Using placeholder.")
    return "https://your-api-gateway-url.amazonaws.com/Prod"


def load_frontend_env() -> dict:
    """Load frontend environment variables."""
    env_vars = {}
    env_path = Path("frontend/.env")

    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    if key.startswith("VITE_"):
                        env_vars[key[5:]] = value.strip('"')  # Remove VITE_ prefix and quotes

    return env_vars


def update_frontend_env(api_url: str) -> None:
    """Update frontend .env file with API URL from deployment."""
    env_path = Path("frontend/.env")
    if not env_path.exists():
        print("[WARN] frontend/.env not found, skipping update")
        return

    # Read current .env file
    lines = []
    with open(env_path) as f:
        lines = f.readlines()

    # Update API URL line
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("VITE_API_BASE_URL="):
            lines[i] = f"VITE_API_BASE_URL={api_url}\n"
            updated = True
            break

    if not updated:
        lines.append(f"VITE_API_BASE_URL={api_url}\n")

    # Write back to file
    with open(env_path, "w") as f:
        f.writelines(lines)

    print(f"[OK] Updated frontend/.env with API URL: {api_url}")


def generate_config(stack_name: str, environment: str) -> None:
    """Generate frontend config.js file."""
    print("[INFO] Generating frontend configuration...")

    api_url = get_stack_output(stack_name)
    update_frontend_env(api_url)  # Update .env file with API URL
    env_vars = load_frontend_env()

    # Convert string booleans to JavaScript booleans
    def to_js_bool(value: str) -> str:
        return "true" if value.lower() in ["true", "1", "yes"] else "false"

    config_content = f'''// CloudOps Assistant Frontend Configuration
// Generated automatically - DO NOT EDIT MANUALLY
// Update frontend/.env to change these values

window.CONFIG = {{
    // API Configuration
    API_BASE_URL: '{api_url}',

    // App Configuration
    APP_NAME: '{env_vars.get("APP_NAME", "CloudOps Assistant")}',
    VERSION: '{env_vars.get("VERSION", "1.0.0")}',
    ENVIRONMENT: '{environment}',

    // Feature Flags
    FEATURES: {{
        DRIFT_DETECTION: {to_js_bool(env_vars.get("ENABLE_DRIFT_DETECTION", "true"))},
        COST_DASHBOARD: {to_js_bool(env_vars.get("ENABLE_COST_DASHBOARD", "true"))},
        AI_FEATURES: {to_js_bool(env_vars.get("ENABLE_AI_FEATURES", "true"))}
    }},

    // Security
    MAX_FILE_SIZE: {env_vars.get("MAX_FILE_SIZE", "10485760")},
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration
    GITHUB_TARGETS: '{env_vars.get("GITHUB_TARGETS", "your-github-username")}',

    // Utility Functions
    sanitizeInput: function(input) {{
        if (typeof input !== 'string') return input;
        return input.replace(/[<>\\"'&]/g, '').substring(0, 1000);
    }}
}};

console.log('CloudOps Assistant Config Loaded:', window.CONFIG.ENVIRONMENT);
console.log('API Base URL:', window.CONFIG.API_BASE_URL);
'''

    # Write config.js
    config_path = Path("frontend/config.js")
    with open(config_path, "w") as f:
        f.write(config_content)

    print("[OK] Frontend configuration generated successfully!")
    print(f"[INFO] API URL: {api_url}")
    print(f"[INFO] Environment: {environment}")
    print(f"[INFO] Config written to: {config_path.absolute()}")
    print(f"[INFO] Frontend .env updated with API URL")


def main():
    parser = argparse.ArgumentParser(description="Generate frontend configuration")
    parser.add_argument("--stack-name", default="cloudops-assistant", help="CloudFormation stack name")
    parser.add_argument("--environment", default="prod", help="Deployment environment")
    parser.add_argument("--local", action="store_true", help="Generate config for local development (no stack lookup)")

    args = parser.parse_args()

    try:
        if args.local:
            # For local development, use placeholder API URL
            print("[INFO] Generating local development configuration...")
            env_vars = load_frontend_env()

            def to_js_bool(value: str) -> str:
                return "true" if value.lower() in ["true", "1", "yes"] else "false"

            config_content = f'''// CloudOps Assistant Frontend Configuration (Local Development)
// Generated automatically - DO NOT EDIT MANUALLY
// Update frontend/.env to change these values

window.CONFIG = {{
    // API Configuration (Local Development)
    API_BASE_URL: 'http://localhost:8080',  // Local development server

    // App Configuration
    APP_NAME: '{env_vars.get("APP_NAME", "CloudOps Assistant")}',
    VERSION: '{env_vars.get("VERSION", "1.0.0")}',
    ENVIRONMENT: 'development',

    // Feature Flags
    FEATURES: {{
        DRIFT_DETECTION: {to_js_bool(env_vars.get("ENABLE_DRIFT_DETECTION", "true"))},
        COST_DASHBOARD: {to_js_bool(env_vars.get("ENABLE_COST_DASHBOARD", "true"))},
        AI_FEATURES: {to_js_bool(env_vars.get("ENABLE_AI_FEATURES", "true"))}
    }},

    // Security
    MAX_FILE_SIZE: {env_vars.get("MAX_FILE_SIZE", "10485760")},
    ALLOWED_FILE_TYPES: ['.txt', '.log', '.out', '.plan'],

    // GitHub Configuration
    GITHUB_TARGETS: '{env_vars.get("GITHUB_TARGETS", "your-github-username")}',

    // Utility Functions
    sanitizeInput: function(input) {{
        if (typeof input !== 'string') return input;
        return input.replace(/[<>\\"'&]/g, '').substring(0, 1000);
    }}
}};

console.log('CloudOps Assistant Config Loaded (Local Dev):', window.CONFIG.ENVIRONMENT);
'''

            config_path = Path("frontend/config.js")
            with open(config_path, "w") as f:
                f.write(config_content)

            print("[OK] Local development configuration generated!")
            print("[INFO] API URL: http://localhost:3001/dev (update as needed)")
        else:
            generate_config(args.stack_name, args.environment)
    except Exception as e:
        print(f"[ERROR] Error generating config: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
