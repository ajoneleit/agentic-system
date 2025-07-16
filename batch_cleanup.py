#!/usr/bin/env python3

import os
import shutil
import sys

def cleanup_projects():
    """
    Remove all directories and files from projects directory except:
    - artifacts/ folder
    - metadata/ folder  
    - index.json file
    """
    
    print("=== Projects Directory Cleanup ===")
    print("This will remove all project directories except artifacts/, metadata/, and index.json")
    
    # Configuration
    base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
    keep_items = ['artifacts', 'metadata', 'index.json']
    
    # Verify base path exists
    if not os.path.exists(base_path):
        print(f"ERROR: Projects directory {base_path} does not exist!")
        return False
    
    print(f"Working in: {base_path}")
    
    try:
        # Get all items in the projects directory
        all_items = os.listdir(base_path)
        print(f"Found {len(all_items)} total items")
        
        # Separate items to keep vs remove
        items_to_keep = []
        items_to_remove = []
        
        for item in all_items:
            if item in keep_items:
                items_to_keep.append(item)
            else:
                items_to_remove.append(item)
        
        print(f"Items to keep ({len(items_to_keep)}): {items_to_keep}")
        print(f"Items to remove ({len(items_to_remove)}): {len(items_to_remove)} items")
        
        # Remove items
        removed_count = 0
        error_count = 0
        
        for item in items_to_remove:
            item_path = os.path.join(base_path, item)
            try:
                if os.path.isdir(item_path):
                    shutil.rmtree(item_path)
                    print(f"  ✓ Removed directory: {item}")
                    removed_count += 1
                else:
                    os.remove(item_path)
                    print(f"  ✓ Removed file: {item}")
                    removed_count += 1
            except Exception as e:
                print(f"  ✗ Error removing {item}: {e}")
                error_count += 1
        
        print(f"\n=== Cleanup Results ===")
        print(f"Successfully removed: {removed_count} items")
        print(f"Errors: {error_count} items")
        
        # Verify final state
        print(f"\n=== Final State ===")
        final_items = os.listdir(base_path)
        print(f"Remaining items ({len(final_items)}):")
        for item in final_items:
            print(f"  {item}")
        
        # Check if we have exactly what we expect
        expected_items = set(keep_items)
        actual_items = set(final_items)
        
        if expected_items == actual_items:
            print(f"\n✓ SUCCESS: Directory now contains exactly the expected items!")
            return True
        else:
            print(f"\n⚠ WARNING: Directory contents don't match expected items")
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

# Auto-execute the cleanup
print("Starting automatic cleanup...")
cleanup_projects()