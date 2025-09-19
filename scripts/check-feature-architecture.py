#!/usr/bin/env python3
"""Check that each feature has a corresponding architecture diagram."""

import os
import re
from pathlib import Path


def extract_features_from_readme():
    """Extract completed features from README.md."""
    readme_path = Path("README.md")
    if not readme_path.exists():
        return []

    features = []
    with open(readme_path) as f:
        content = f.read()

    # Find completed features (marked with ✅)
    pattern = r"- \[x\] \*\*Day (\d+)\*\*: ([^✅]+)✅"
    matches = re.findall(pattern, content)

    for day, feature in matches:
        features.append((int(day), feature.strip()))

    return features


def check_architecture_diagrams():
    """Check that each feature has an architecture diagram."""
    features = extract_features_from_readme()
    arch_dir = Path("architecture")

    if not arch_dir.exists():
        print("❌ Architecture directory not found")
        return False

    missing_diagrams = []

    for day, feature in features:
        # Look for day-specific architecture files
        expected_patterns = [
            f"day{day}-*.svg",
            f"architecture-day{day}.svg"
        ]

        found = False
        for pattern in expected_patterns:
            if list(arch_dir.glob(pattern)):
                found = True
                break

        if not found:
            missing_diagrams.append(f"Day {day}: {feature}")

    if missing_diagrams:
        print("❌ Missing architecture diagrams:")
        for missing in missing_diagrams:
            print(f"   - {missing}")
        return False

    print(f"✅ All {len(features)} completed features have architecture diagrams")
    return True


if __name__ == "__main__":
    success = check_architecture_diagrams()
    exit(0 if success else 1)
