#!/usr/bin/env python3
"""
Final direct cleanup script for projects directory
Executes immediately upon creation
"""
import os
import shutil
import traceback

def run_cleanup():
    """Execute cleanup directly"""
    print("=== FINAL DIRECT CLEANUP EXECUTION ===")
    
    # Project settings
    base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
    keep_items = ['artifacts', 'metadata', 'index.json']
    
    try:
        # Check if directory exists
        if not os.path.exists(base_path):
            print(f"ERROR: Directory {base_path} does not exist!")
            return False
        
        # Get all items
        all_items = os.listdir(base_path)
        print(f"Found {len(all_items)} items in projects directory")
        
        # Process each item
        removed_count = 0
        keep_count = 0
        error_count = 0
        
        for item in all_items:
            item_path = os.path.join(base_path, item)
            
            if item in keep_items:
                print(f"KEEP: {item}")
                keep_count += 1
            else:
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"REMOVED DIR: {item}")
                        removed_count += 1
                    else:
                        os.remove(item_path)
                        print(f"REMOVED FILE: {item}")
                        removed_count += 1
                except Exception as e:
                    print(f"ERROR removing {item}: {e}")
                    error_count += 1
        
        print(f"\n=== CLEANUP SUMMARY ===")
        print(f"Items kept: {keep_count}")
        print(f"Items removed: {removed_count}")
        print(f"Errors: {error_count}")
        
        # Final verification
        final_items = os.listdir(base_path)
        print(f"\n=== FINAL STATE ===")
        print(f"Items remaining: {len(final_items)}")
        for item in final_items:
            print(f"  - {item}")
        
        # Check success
        expected = set(keep_items)
        actual = set(final_items)
        
        if expected == actual:
            print(f"\n✓ SUCCESS: Directory contains exactly: {expected}")
            return True
        else:
            print(f"\n⚠ PARTIAL SUCCESS:")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")
            return False
            
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        traceback.print_exc()
        return False

# Execute cleanup immediately
if __name__ == "__main__":
    success = run_cleanup()
    print(f"\n{'='*50}")
    if success:
        print("✓ CLEANUP COMPLETED SUCCESSFULLY")
    else:
        print("⚠ CLEANUP FINISHED WITH ISSUES")
    print(f"{'='*50}")

# Auto-execute on file creation
try:
    run_cleanup()
except Exception as e:
    print(f"Auto-execution failed: {e}")