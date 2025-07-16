import os
import shutil

# Define the cleanup function inline
def cleanup_projects():
    base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
    keep_items = ['artifacts', 'metadata', 'index.json']
    
    try:
        # Get all items in the projects directory
        items = os.listdir(base_path)
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
        
        print(f"\nCleanup complete. Removed {removed_count} items.")
        
        # List remaining items
        print("\nRemaining items:")
        remaining = os.listdir(base_path)
        for item in remaining:
            print(f"  {item}")
        
        return True
        
    except Exception as e:
        print(f"Error during cleanup: {e}")
        return False

# Execute cleanup
if __name__ == "__main__":
    cleanup_projects()