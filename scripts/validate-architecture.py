#!/usr/bin/env python3
"""
Validate architecture diagrams for CloudOps Assistant
Ensures architecture SVGs exist for significant changes
"""

import os
import sys
import subprocess
from pathlib import Path


def get_changed_files():
    """Get list of changed files from git"""
    try:
        result = subprocess.run(
            ['git', 'diff', '--name-only', 'HEAD~1'],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip().split('\n') if result.stdout.strip() else []
    except subprocess.CalledProcessError:
        # If git diff fails, assume we're in initial commit
        return []


def check_architecture_diagrams():
    """Check if architecture diagrams exist and are up to date"""
    architecture_dir = Path("architecture")
    
    if not architecture_dir.exists():
        print("❌ Architecture directory not found")
        return False
    
    # Check if required architecture files exist
    required_files = [
        "day5-jwt-authentication.svg"
    ]
    
    missing_files = []
    for file in required_files:
        if not (architecture_dir / file).exists():
            missing_files.append(file)
    
    if missing_files:
        print("❌ Missing architecture diagrams:")
        for file in missing_files:
            print(f"   - architecture/{file}")
        return False
    
    print("✅ Architecture diagrams check passed")
    return True


def check_template_changes():
    """Check if template.yaml changes require architecture updates"""
    changed_files = get_changed_files()
    
    if 'template.yaml' in changed_files:
        print("ℹ️  template.yaml was modified")
        
        # Check if corresponding architecture diagram exists
        architecture_dir = Path("architecture")
        svg_files = list(architecture_dir.glob("*.svg"))
        
        if not svg_files:
            print("❌ template.yaml changed but no architecture diagrams found")
            return False
        
        print("✅ Architecture diagrams exist for template changes")
    
    return True


def main():
    """Main function"""
    success = True
    
    success &= check_architecture_diagrams()
    success &= check_template_changes()
    
    if not success:
        print("\n❌ Architecture validation failed")
        sys.exit(1)
    
    print("\n✅ All architecture checks passed")


if __name__ == "__main__":
    main()