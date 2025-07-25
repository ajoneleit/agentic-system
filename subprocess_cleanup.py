#!/usr/bin/env python3

import os
import shutil
import subprocess
import sys


def cleanup_projects():
    """Remove all project directories except artifacts/, metadata/, and index.json"""
    print("=== Projects Directory Cleanup ===")

    # Configuration
    base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
    keep_items = ['artifacts', 'metadata', 'index.json']

    try:
        # Check if projects directory exists
        if not os.path.exists(base_path):
            print(f"ERROR: Projects directory {base_path} does not exist!")
            return False

        # Get all items in the projects directory
        all_items = os.listdir(base_path)
        print(f"Found {len(all_items)} total items")

        # Remove items that are not in keep_items
        removed_count = 0
        error_count = 0

        for item in all_items:
            if item not in keep_items:
                item_path = os.path.join(base_path, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"✓ Removed directory: {item}")
                        removed_count += 1
                    else:
                        os.remove(item_path)
                        print(f"✓ Removed file: {item}")
                        removed_count += 1
                except Exception as e:
                    print(f"✗ Error removing {item}: {e}")
                    error_count += 1
            else:
                print(f"→ Keeping: {item}")

        print("\n=== Cleanup Results ===")
        print(f"Successfully removed: {removed_count} items")
        print(f"Errors: {error_count} items")

        # Show final state
        print("\n=== Final State ===")
        final_items = os.listdir(base_path)
        print(f"Remaining items ({len(final_items)}):")
        for item in final_items:
            print(f"  {item}")

        # Check if we have exactly what we expect
        expected_items = set(keep_items)
        actual_items = set(final_items)

        if expected_items == actual_items:
            print("\n✓ SUCCESS: Directory now contains exactly the expected items!")
            return True
        else:
            print("\n⚠ WARNING: Directory contents don't match expected items")
            print(f"Expected: {expected_items}")
            print(f"Actual: {actual_items}")
            return False

    except Exception as e:
        print(f"ERROR during cleanup: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = cleanup_projects()
    sys.exit(0 if success else 1)

# Try to execute using subprocess
try:
    result = subprocess.run([sys.executable, __file__], capture_output=True, text=True,
                          cwd='/mnt/c/Users/ajoneleit/agentic-system')
    print("STDOUT:")
    print(result.stdout)
    print("\nSTDERR:")
    print(result.stderr)
    print(f"\nReturn code: {result.returncode}")
except Exception as e:
    print(f"Subprocess execution failed: {e}")
    # Fall back to direct execution
    cleanup_projects()
