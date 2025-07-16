#!/usr/bin/env python3
"""Quick validation that the EvolutionaryAgent fix works."""

import sys
from pathlib import Path
from uuid import uuid4

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all required imports work."""
    try:
        print("🔍 Testing imports...")
        
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        from src.core.result import Result
        from src.core.task_result import TaskResult
        
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        return False

def test_instantiation():
    """Test that EvolutionaryAgent can be instantiated."""
    try:
        print("🔍 Testing EvolutionaryAgent instantiation...")
        
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        
        # This should not raise "Can't instantiate abstract class" error
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )
        
        print("✅ EvolutionaryAgent instantiated successfully")
        print(f"  Agent ID: {agent.id}")
        print(f"  Role: {agent.role}")
        print(f"  Evolution enabled: {agent.evolution_enabled}")
        return True
        
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_method_exists():
    """Test that _execute_specific_task method exists and is callable."""
    try:
        print("🔍 Testing _execute_specific_task method...")
        
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )
        
        # Check method exists
        assert hasattr(agent, '_execute_specific_task')
        print("✅ Method _execute_specific_task exists")
        
        # Check it's callable
        assert callable(agent._execute_specific_task)
        print("✅ Method is callable")
        
        # Check it's async
        import inspect
        assert inspect.iscoroutinefunction(agent._execute_specific_task)
        print("✅ Method is async")
        
        return True
        
    except Exception as e:
        print(f"❌ Method test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_zero_import():
    """Test that zero.py can be imported."""
    try:
        print("🔍 Testing zero.py import...")
        
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

def main():
    """Run validation tests."""
    print("🚀 Validating EvolutionaryAgent Fix...")
    print("=" * 50)
    
    tests = [
        ("Imports", test_imports),
        ("Instantiation", test_instantiation),
        ("Method Exists", test_method_exists),
        ("Zero Import", test_zero_import),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print(f"\n{'='*50}")
    print(f"📊 FINAL RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL VALIDATION TESTS PASSED!")
        print("\nThe EvolutionaryAgent abstract method implementation is working correctly.")
        return True
    else:
        print("⚠️  Some validation tests failed.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)