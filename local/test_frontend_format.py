#!/usr/bin/env python3
"""
Test the frontend formatSource function logic
"""

def test_format_source():
    """Test the formatSource function logic"""

    # Test URL from our debug data
    test_url = "https://github.com/rmnicholson0612/FocusFlow/blob/main/backend/functions/preferences/package.json#L7"

    print(f"Original URL: {test_url}")

    # Current logic (problematic)
    parts = test_url.split('/')
    print(f"URL parts: {parts}")

    filename_current = parts[-1].split('#')[0] if parts else 'View'
    print(f"Current filename extraction: {filename_current}")

    # Better logic - extract meaningful path
    if 'github.com' in test_url and '/blob/' in test_url:
        # Extract path after /blob/main/ or /blob/master/
        blob_index = test_url.find('/blob/')
        if blob_index != -1:
            after_blob = test_url[blob_index + 6:]  # Skip '/blob/'
            # Skip branch name (usually main or master)
            if '/' in after_blob:
                file_path = '/'.join(after_blob.split('/')[1:])  # Skip branch name
                file_path = file_path.split('#')[0]  # Remove line number
                print(f"Better extraction: {file_path}")

                # Even better - show just filename with line number
                filename = file_path.split('/')[-1]
                line_part = test_url.split('#')[1] if '#' in test_url else ''
                if line_part:
                    display_name = f"{filename}#{line_part}"
                else:
                    display_name = filename
                print(f"Best display name: {display_name}")

if __name__ == "__main__":
    test_format_source()
