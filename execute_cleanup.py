import os
import shutil
import subprocess
import sys

# Try to execute the cleanup directly
try:
    # First, try to execute the cleanup script directly
    exec(open('/mnt/c/Users/ajoneleit/agentic-system/direct_cleanup.py').read())
except Exception as e:
    print(f"Error executing cleanup: {e}")

    # If that fails, try using subprocess
    try:
        result = subprocess.run([sys.executable, '/mnt/c/Users/ajoneleit/agentic-system/direct_cleanup.py'],
                               capture_output=True, text=True, cwd='/mnt/c/Users/ajoneleit/agentic-system')
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
        print("Return code:", result.returncode)
    except Exception as e2:
        print(f"Subprocess also failed: {e2}")

        # Manual cleanup as fallback
        print("Attempting manual cleanup...")
        base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'

        # Get all items
        items = os.listdir(base_path)
        keep_items = ['artifacts', 'metadata', 'index.json']

        for item in items:
            if item not in keep_items:
                item_path = os.path.join(base_path, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                        print(f"Removed directory: {item}")
                    else:
                        os.remove(item_path)
                        print(f"Removed file: {item}")
                except Exception as e3:
                    print(f"Error removing {item}: {e3}")
