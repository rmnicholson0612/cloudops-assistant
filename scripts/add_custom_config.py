#!/usr/bin/env python3
"""
Helper script to add custom configuration to frontend config.js
Usage: python scripts/add_custom_config.py "CUSTOM_KEY: 'value',"
"""

import sys
import re
from pathlib import Path

def add_custom_config(config_line):
    """Add custom configuration to config.js"""
    config_path = Path("frontend/config.js")

    if not config_path.exists():
        print("Error: frontend/config.js not found")
        return False

    # Read current config
    with open(config_path, 'r') as f:
        content = f.read()

    # Find custom config section
    start_marker = "// {{CUSTOM_CONFIG_START}}"
    end_marker = "// {{CUSTOM_CONFIG_END}}"

    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)

    if start_idx == -1 or end_idx == -1:
        print("Error: Custom config markers not found in config.js")
        return False

    # Insert the new config line
    before = content[:start_idx + len(start_marker)]
    after = content[end_idx:]

    # Get existing custom config
    existing_custom = content[start_idx + len(start_marker):end_idx].strip()

    # Add new config
    if existing_custom and not existing_custom.endswith(','):
        config_line = ',' + config_line

    new_content = before + "\n    " + config_line + "\n    " + after

    # Write back
    with open(config_path, 'w') as f:
        f.write(new_content)

    print(f"✅ Added custom config: {config_line}")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/add_custom_config.py \"CUSTOM_KEY: 'value',\"")
        sys.exit(1)

    config_line = sys.argv[1]
    if add_custom_config(config_line):
        print("Custom configuration added successfully!")
        print("Run 'make serve-frontend' to regenerate with your custom config preserved.")
    else:
        sys.exit(1)
