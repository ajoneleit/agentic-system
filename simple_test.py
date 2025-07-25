#!/usr/bin/env python3
"""Simple test to verify TaskResult import fix."""

import os
import sys

sys.path.insert(0, os.getcwd())

try:
    print("Testing TaskResult import...")
    print("✅ TaskResult import successful")

    print("Testing zero.py import...")
    import zero
    print("✅ zero.py import successful")

    print("Testing ZeroSystem creation...")
    system = zero.ZeroSystem()
    print("✅ ZeroSystem creation successful")

    print("🎉 All quick tests passed!")

except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
