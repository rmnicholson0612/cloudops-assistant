#!/usr/bin/env python3
"""Bootstrap script for complete CloudOps Assistant setup."""

import subprocess
import sys
from pathlib import Path


def run_command(cmd: list, description: str) -> bool:
    """Run a command and return success status."""
    print(f"🔧 {description}...")
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False
    except FileNotFoundError:
        print(f"❌ Command not found: {' '.join(cmd)}")
        return False


def check_prerequisites() -> bool:
    """Check if required tools are installed."""
    print("🔍 Checking prerequisites...")

    checks = [
        (["aws", "--version"], "AWS CLI"),
        (["sam", "--version"], "SAM CLI"),
        (["python", "--version"], "Python"),
        (["git", "--version"], "Git")
    ]

    all_good = True
    for cmd, name in checks:
        if not run_command(cmd, f"Checking {name}"):
            all_good = False

    return all_good


def setup_environment() -> bool:
    """Setup environment files from templates."""
    print("📝 Setting up environment files...")

    env_files = [
        ("backend/.env.example", "backend/.env"),
        ("frontend/.env.example", "frontend/.env")
    ]

    for template, env_file in env_files:
        template_path = Path(template)
        env_path = Path(env_file)

        if not template_path.exists():
            print(f"❌ Template {template} not found")
            return False

        if not env_path.exists():
            env_path.write_text(template_path.read_text())
            print(f"✅ Created {env_file} from template")
        else:
            print(f"ℹ️  {env_file} already exists")

    return True


def install_dependencies() -> bool:
    """Install Python dependencies."""
    print("📦 Installing Python dependencies...")

    # Check if requirements files exist
    req_files = ["requirements.txt", "requirements-dev.txt"]
    for req_file in req_files:
        if Path(req_file).exists():
            if not run_command(["pip", "install", "-r", req_file], f"Installing {req_file}"):
                return False

    return True


def validate_aws_config() -> bool:
    """Validate AWS configuration."""
    print("🔐 Validating AWS configuration...")

    # Check AWS credentials
    if not run_command(["aws", "sts", "get-caller-identity"], "Checking AWS credentials"):
        print("💡 Run 'aws configure' to set up your AWS credentials")
        return False

    return True


def main():
    """Main bootstrap process."""
    print("🚀 CloudOps Assistant Bootstrap")
    print("=" * 50)

    steps = [
        (check_prerequisites, "Prerequisites check"),
        (setup_environment, "Environment setup"),
        (install_dependencies, "Dependency installation"),
        (validate_aws_config, "AWS configuration validation")
    ]

    for step_func, step_name in steps:
        if not step_func():
            print(f"\n❌ Bootstrap failed at: {step_name}")
            print("Please fix the issues above and run 'make bootstrap' again.")
            sys.exit(1)

    print("\n🎉 Bootstrap completed successfully!")
    print("\nNext steps:")
    print("1. Edit backend/.env and frontend/.env with your configuration")
    print("2. Run 'make deploy-guided' for first-time deployment")
    print("3. Run 'make deploy' for subsequent deployments")
    print("\nSee DEPLOYMENT.md for detailed instructions.")


if __name__ == "__main__":
    main()
