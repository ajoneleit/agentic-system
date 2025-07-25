import os
import shutil

# Execute cleanup immediately when this file is created
base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
keep_items = ['artifacts', 'metadata', 'index.json']

print("Starting immediate cleanup...")

try:
    # Check if projects directory exists
    if not os.path.exists(base_path):
        print(f"Error: Projects directory {base_path} does not exist!")
    else:
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
        print("\nRemaining items in projects directory:")
        remaining = os.listdir(base_path)
        for item in remaining:
            print(f"  {item}")

        print("\nCleanup finished successfully!")

except Exception as e:
    print(f"Error during cleanup: {e}")
    import traceback
    traceback.print_exc()
