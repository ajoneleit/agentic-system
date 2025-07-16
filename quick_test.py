#!/usr/bin/env python3
"""Quick test to verify TaskResult import fix."""

try:
    print("Testing TaskResult import...")
    from src.core.interfaces import TaskResult
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
    exit(1)