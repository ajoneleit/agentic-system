import os
import sys

print("Python version:", sys.version)
print("Current working directory:", os.getcwd())
print("Python path:", sys.path)

# Test basic file operations
test_path = '/mnt/c/Users/ajoneleit/agentic-system/projects'
print(f"Projects directory exists: {os.path.exists(test_path)}")

if os.path.exists(test_path):
    try:
        items = os.listdir(test_path)
        print(f"Number of items in projects directory: {len(items)}")
        print("First few items:", items[:5])
    except Exception as e:
        print(f"Error listing directory: {e}")
else:
    print("Projects directory does not exist!")

# Check specific items
artifacts_path = os.path.join(test_path, 'artifacts')
metadata_path = os.path.join(test_path, 'metadata')
index_path = os.path.join(test_path, 'index.json')

print(f"Artifacts directory exists: {os.path.exists(artifacts_path)}")
print(f"Metadata directory exists: {os.path.exists(metadata_path)}")
print(f"Index.json exists: {os.path.exists(index_path)}")

print("Environment test complete.")