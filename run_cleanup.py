#!/usr/bin/env python3
import os
import subprocess
import sys

# Change to the directory containing the cleanup script
os.chdir('/mnt/c/Users/ajoneleit/agentic-system')

# Run the cleanup script
result = subprocess.run([sys.executable, 'direct_cleanup.py'], capture_output=True, text=True)

print("STDOUT:")
print(result.stdout)
print("\nSTDERR:")
print(result.stderr)
print(f"\nReturn code: {result.returncode}")
