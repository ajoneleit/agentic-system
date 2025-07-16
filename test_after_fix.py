#!/usr/bin/env python3
"""Test to verify the TaskResult import fix."""

def test_taskresult_import():
    """Test that TaskResult can be imported from interfaces."""
    try:
        from src.core.interfaces import TaskResult
        print("✅ TaskResult imported successfully from interfaces")
        
        # Test TaskResult instantiation
        from uuid import uuid4
        task_result = TaskResult(
            task_id=uuid4(),
            agent_id=uuid4(),
            success=True
        )
        print("✅ TaskResult instantiated successfully")
        
        # Test that it has the expected methods
        assert hasattr(task_result, 'add_artifact')
        assert hasattr(task_result, 'add_error')
        assert hasattr(task_result, 'add_warning')
        assert hasattr(task_result, 'set_metrics')
        print("✅ TaskResult has all expected methods")
        
        return True
        
    except Exception as e:
        print(f"❌ TaskResult import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_zero_import():
    """Test that zero.py can be imported."""
    try:
        import zero
        print("✅ zero.py imported successfully")
        
        # Test ZeroSystem creation
        system = zero.ZeroSystem()
        print("✅ ZeroSystem created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ zero.py import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🔍 Testing TaskResult import fix...")
    
    success = True
    
    if not test_taskresult_import():
        success = False
    
    if not test_zero_import():
        success = False
    
    if success:
        print("\n🎉 All tests passed! TaskResult import is fixed.")
    else:
        print("\n❌ Some tests failed.")