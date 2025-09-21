#!/usr/bin/env python3
"""
Update badges and progress tracker in README.md
Automatically updates day counter and progress percentages
"""

import re
import sys
from pathlib import Path
from datetime import datetime


def get_current_day():
    """Calculate current day based on completed features"""
    # Count completed days from README
    readme_path = Path("README.md")
    content = readme_path.read_text(encoding='utf-8')

    # Count completed items (marked with ✅ COMPLETE)
    completed_pattern = r'- \[x\].*✅ COMPLETE'
    completed_count = len(re.findall(completed_pattern, content))

    return completed_count


def update_day_badge(content, current_day):
    """Update the day badge in README"""
    day_pattern = r'Day-(\d+)%2F30'
    new_badge = f'Day-{current_day}%2F30'

    updated_content = re.sub(day_pattern, new_badge, content)
    return updated_content


def update_progress_tracker(content, current_day):
    """Update the progress tracker section"""
    total_days = 30
    overall_percentage = (current_day / total_days) * 100

    # Calculate foundation progress (7 days)
    foundation_completed = min(current_day, 7)
    foundation_percentage = (foundation_completed / 7) * 100

    # Create progress bars
    foundation_bar = "█" * int(foundation_percentage / 2) + "░" * (50 - int(foundation_percentage / 2))
    overall_bar = "█" * int(overall_percentage / 10) + "░" * (10 - int(overall_percentage / 10))

    progress_section = f"""```
Foundation:    {foundation_bar} {foundation_percentage:.1f}% ({foundation_completed}/7 days)
AI Layer:      ░░░░░░░░░░  0% (0/7 days)
Observability: ░░░░░░░░░░  0% (0/7 days)
Advanced:      ░░░░░░░░░░  0% (0/9 days)

Overall:       {overall_bar} {overall_percentage:.1f}% ({current_day}/30 days)
```"""

    # Replace existing progress tracker
    pattern = r'```\nFoundation:.*?\n```'
    updated_content = re.sub(pattern, progress_section, content, flags=re.DOTALL)

    return updated_content


def update_current_features_section(content, current_day):
    """Update the current features section header"""
    pattern = r'## 📈 Current Features \(Day \d+\)'
    replacement = f'## 📈 Current Features (Day {current_day})'

    updated_content = re.sub(pattern, replacement, content)
    return updated_content


def main():
    """Main function"""
    readme_path = Path("README.md")

    if not readme_path.exists():
        print("README.md not found")
        sys.exit(1)

    content = readme_path.read_text(encoding='utf-8')
    current_day = get_current_day()

    print(f"Current day: {current_day}")

    # Update all sections
    content = update_day_badge(content, current_day)
    content = update_progress_tracker(content, current_day)
    content = update_current_features_section(content, current_day)

    # Write back to file
    readme_path.write_text(content, encoding='utf-8')

    print("README.md badges and progress updated")


if __name__ == "__main__":
    main()
