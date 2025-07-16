#!/usr/bin/env python3

import os
import shutil

# Path to the projects directory
projects_dir = '/mnt/c/Users/ajoneleit/agentic-system/projects'

# List of directories/files to keep
keep_items = ['artifacts', 'metadata', 'index.json']

try:
    # Get all items in the projects directory
    items = os.listdir(projects_dir)
    
    removed_items = []
    
    for item in items:
        item_path = os.path.join(projects_dir, item)
        
        # Skip if it's one of the items we want to keep
        if item in keep_items:
            print(f"Keeping: {item}")
            continue
        
        # Remove the item
        if os.path.isdir(item_path):
            shutil.rmtree(item_path)
            removed_items.append(f"Directory: {item}")
        else:
            os.remove(item_path)
            removed_items.append(f"File: {item}")
        
        print(f"Removed: {item}")
    
    print(f"\nCleanup complete. Removed {len(removed_items)} items.")
    
    # List remaining items
    print("\nRemaining items in projects directory:")
    remaining_items = os.listdir(projects_dir)
    for item in remaining_items:
        print(f"  {item}")
    
except Exception as e:
    print(f"Error during cleanup: {e}")