import os
import shutil

base_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'

# Remove one directory at a time
directories = ['calculator', 'calculator_2', 'calculator_3', 'calculator_4', 'calculator_5']

for dir_name in directories:
    full_path = os.path.join(base_path, dir_name)
    try:
        if os.path.exists(full_path):
            shutil.rmtree(full_path)
            print(f"Removed: {dir_name}")
    except Exception as e:
        print(f"Error removing {dir_name}: {e}")

print("Done with first batch")