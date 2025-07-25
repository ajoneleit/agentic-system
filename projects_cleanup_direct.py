#!/usr/bin/env python3
"""Direct cleanup of projects directory."""

import shutil
from pathlib import Path

# Define the projects directory
projects_dir = Path("/mnt/c/Users/ajoneleit/agentic-system/projects")

print(f"Starting cleanup of {projects_dir}")

# Items to keep
keep_items = {'artifacts', 'index.json', 'metadata'}

# Get all items in projects directory
try:
    all_items = list(projects_dir.iterdir())
    print(f"Found {len(all_items)} items in projects directory")

    for item in all_items:
        if item.name in keep_items:
            print(f"KEEPING: {item.name}")
        else:
            print(f"REMOVING: {item.name}")
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                print(f"  ✅ Successfully removed {item.name}")
            except Exception as e:
                print(f"  ❌ Error removing {item.name}: {e}")

    # Show final state
    remaining = list(projects_dir.iterdir())
    print(f"\n📁 Final state - {len(remaining)} items remaining:")
    for item in sorted(remaining):
        print(f"  - {item.name}")

except Exception as e:
    print(f"Error during cleanup: {e}")

print("Cleanup complete!")
