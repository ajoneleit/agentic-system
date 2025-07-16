import os
import shutil

# Execute cleanup immediately
base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
keep_items = ['artifacts', 'metadata', 'index.json']

print("=== Executing Immediate Cleanup ===")

try:
    if os.path.exists(base_path):
        all_items = os.listdir(base_path)
        print(f"Found {len(all_items)} total items")
        
        removed_count = 0
        for item in all_items:
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
        
        print(f"\nRemoved {removed_count} items")
        
        # Show final state
        final_items = os.listdir(base_path)
        print(f"Remaining items ({len(final_items)}):")
        for item in final_items:
            print(f"  {item}")
            
        if set(final_items) == set(keep_items):
            print("SUCCESS: Cleanup completed successfully!")
        else:
            print("WARNING: Unexpected items remain")
            
    else:
        print(f"ERROR: {base_path} does not exist")
        
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("=== Cleanup Complete ===")