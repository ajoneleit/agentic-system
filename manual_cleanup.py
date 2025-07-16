#!/usr/bin/env python3

import os
import shutil

print("Starting manual cleanup...")

# Base path
base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
keep_items = ['artifacts', 'metadata', 'index.json']

try:
    # Get all items in the projects directory
    items = os.listdir(base_path)
    print(f"Found {len(items)} items in projects directory")
    
    removed_count = 0
    
    for item in items:
        if item not in keep_items:
            item_path = os.path.join(base_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"Removed directory: {item}")
                    removed_count += 1
                else:
                    os.remove(item_path)
                    print(f"Removed file: {item}")
                    removed_count += 1
            except Exception as e:
                print(f"Error removing {item}: {e}")
        else:
            print(f"Keeping: {item}")
    
    print(f"\nCleanup complete. Removed {removed_count} items.")
    
    # List remaining items
    print("\nRemaining items:")
    remaining = os.listdir(base_path)
    for item in remaining:
        print(f"  {item}")
    
except Exception as e:
    print(f"Error during cleanup: {e}")

print("Manual cleanup finished.")