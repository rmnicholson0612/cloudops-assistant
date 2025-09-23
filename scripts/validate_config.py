#!/usr/bin/env python3
"""Validate configuration synchronization across backend and frontend."""

import os
from pathlib import Path


def load_env_file(path: Path) -> dict:
    """Load environment variables from a file."""
    env_vars = {}
    if not path.exists():
        return env_vars

    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key] = value.strip('"')

    return env_vars


def main():
    """Validate configuration consistency."""
    print("Validating CloudOps Assistant Configuration...")

    # Load environment files
    backend_env = load_env_file(Path("backend/.env"))
    frontend_env = load_env_file(Path("frontend/.env"))

    issues = []

    # Check required backend variables
    required_backend = [
        "ENVIRONMENT", "AWS_REGION", "STACK_NAME",
        "BEDROCK_MODEL", "BEDROCK_COMPLEX_MODEL", "BEDROCK_SIMPLE_MODEL"
    ]

    for var in required_backend:
        if var not in backend_env or not backend_env[var]:
            issues.append(f"Missing backend variable: {var}")

    # Check required frontend variables
    required_frontend = [
        "VITE_APP_NAME", "VITE_VERSION", "VITE_ENVIRONMENT",
        "VITE_ENABLE_DRIFT_DETECTION", "VITE_ENABLE_COST_DASHBOARD", "VITE_ENABLE_AI_FEATURES"
    ]

    for var in required_frontend:
        if var not in frontend_env or not frontend_env[var]:
            issues.append(f"Missing frontend variable: {var}")

    # Check API URL is set (after deployment)
    if "VITE_API_BASE_URL" in frontend_env:
        api_url = frontend_env["VITE_API_BASE_URL"]
        if "your-api-gateway-url" in api_url:
            issues.append("Frontend API URL not updated (run 'make update-config' after deployment)")

    # Report results
    if issues:
        print("\\n".join(issues))
        print(f"\\nFound {len(issues)} configuration issues")
        return 1
    else:
        print("All configuration checks passed!")
        print(f"Backend variables: {len(backend_env)}")
        print(f"Frontend variables: {len(frontend_env)}")
        return 0


if __name__ == "__main__":
    exit(main())
