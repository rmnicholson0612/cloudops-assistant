#!/usr/bin/env python3
"""Check if required environment files exist and create from templates if needed."""

import sys
from pathlib import Path

# Fix Windows console encoding issues
if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.detach())


def check_env_file(env_path: Path, template_path: Path) -> bool:
    """Check if env file exists, create from template if not."""
    if env_path.exists():
        return True

    if not template_path.exists():
        print(f"❌ {template_path} not found. Cannot create {env_path}")
        return False

    # Copy template to env file
    template_path.read_text()  # Validate template is readable
    env_path.write_text(template_path.read_text())

    print(f"[OK] Created {env_path} from template")
    print(f"[INFO] Please review and update {env_path} before deploying")
    return False  # Return False to indicate setup needed


def main():
    """Check required environment files."""
    backend_env = Path("backend/.env")
    backend_template = Path("backend/.env.example")

    frontend_env = Path("frontend/.env")
    frontend_template = Path("frontend/.env.example")

    backend_ok = check_env_file(backend_env, backend_template)
    frontend_ok = check_env_file(frontend_env, frontend_template)

    if not (backend_ok and frontend_ok):
        print("\n[WARN] Environment setup required. Please review .env files and run make deploy again.")
        sys.exit(1)

    print("[OK] Environment files ready")


if __name__ == "__main__":
    main()
