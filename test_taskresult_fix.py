#!/usr/bin/env python3
"""Test script to verify TaskResult import fix."""

import sys

def test_taskresult_import():
    """Test that TaskResult can be imported correctly."""
    try:
        # Test import from the old way (should still work)
        from src.core.interfaces import TaskResult
        print("✅ TaskResult import from interfaces: OK")
        
        # Test import from the new way
        from src.core.task_result import TaskResult as TaskResult2
        print("✅ TaskResult import from task_result: OK")
        
        # Verify they're the same class
        if TaskResult is TaskResult2:
            print("✅ TaskResult classes are identical: OK")
        else:
            print("❌ TaskResult classes are different - this may cause issues")
            
        # Test that evolutionary agent can import properly
        from src.agents.evolutionary_agent import EvolutionaryAgent
        print("✅ EvolutionaryAgent import: OK")
        
        # Test zero.py import (the main issue)
        import zero
        print("✅ zero.py import: OK")
        
        print("\n🎉 All TaskResult imports fixed successfully!")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    print("Testing TaskResult import fix...")
    success = test_taskresult_import()
    sys.exit(0 if success else 1)