import os
import shutil

# Execute the cleanup code directly
code = '''
import os
import shutil

base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
keep_items = ['artifacts', 'metadata', 'index.json']

try:
    items = os.listdir(base_path)
    print(f"Found {len(items)} items")
    
    for item in items:
        if item not in keep_items:
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path):
                shutil.rmtree(item_path)
                print(f"Removed directory: {item}")
            else:
                os.remove(item_path)
                print(f"Removed file: {item}")
        else:
            print(f"Keeping: {item}")
    
    print("\\nRemaining items:")
    remaining = os.listdir(base_path)
    for item in remaining:
        print(f"  {item}")
        
except Exception as e:
    print(f"Error: {e}")
'''

exec(code)