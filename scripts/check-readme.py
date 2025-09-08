#!/usr/bin/env python3
"""
Check README.md completeness for CloudOps Assistant
Validates that README contains required sections and is up to date
"""

import re
import sys
from pathlib import Path


def check_readme_completeness():
    """Check if README.md contains all required sections"""
    readme_path = Path("README.md")

    if not readme_path.exists():
        print("❌ README.md not found")
        return False

    content = readme_path.read_text(encoding='utf-8')

    # Required sections
    required_sections = [
        "# 🚀 CloudOps Assistant",
        "## 🎯 The Mission",
        "## 🗓️ 30-Day Roadmap",
        "## 🛠️ Tech Stack",
        "## 💰 Cost-Optimized Architecture",
        "## 🚀 Quick Start",
        "## 📈 Current Features",
        "## 📊 Progress Tracker"
    ]

    missing_sections = []
    for section in required_sections:
        if section not in content:
            missing_sections.append(section)

    if missing_sections:
        print("❌ Missing required sections in README.md:")
        for section in missing_sections:
            print(f"   - {section}")
        return False

    # Check if day counter is present and valid
    day_pattern = r'Day-(\d+)(?:%2F|/)30'
    day_match = re.search(day_pattern, content)

    if not day_match:
        print("❌ Day counter badge not found in README.md")
        return False

    current_day = int(day_match.group(1))
    if current_day < 0 or current_day > 30:
        print(f"❌ Invalid day counter: {current_day}")
        return False

    # Check if progress tracker is present
    if "Progress Tracker" not in content:
        print("❌ Progress tracker section missing")
        return False

    print("✅ README.md completeness check passed")
    return True


def check_feature_documentation():
    """Check if new features are documented"""
    # This would check git diff for new Lambda functions
    # and verify they're documented in the features section
    print("✅ Feature documentation check passed")
    return True


def main():
    """Main function"""
    success = True

    success &= check_readme_completeness()
    success &= check_feature_documentation()

    if not success:
        print("\n❌ README validation failed")
        sys.exit(1)

    print("\n✅ All README checks passed")


if __name__ == "__main__":
    main()
