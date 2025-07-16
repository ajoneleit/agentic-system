#!/usr/bin/env python3
"""Comprehensive validation of all EvolutionaryAgent fixes."""

import sys
import asyncio
from pathlib import Path
from uuid import uuid4

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all imports work correctly."""
    print("🔍 Testing imports...")
    try:
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole, Task, TaskContext, Artifact, ArtifactType
        from src.core.result import Result
        from src.core.task_result import TaskResult
        from src.core.exceptions import TaskExecutionError
        from uuid import UUID
        print("✅ All imports successful")
        return True
    except Exception as e:
        print(f"❌ Import test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_instantiation():
    """Test EvolutionaryAgent instantiation."""
    print("\n🔍 Testing EvolutionaryAgent instantiation...")
    try:
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )
        
        print("✅ EvolutionaryAgent instantiated successfully")
        print(f"  - Agent ID: {agent.id}")
        print(f"  - Role: {agent.role}")
        print(f"  - Evolution enabled: {agent.evolution_enabled}")
        
        # Test attributes
        assert hasattr(agent, 'memory')
        assert hasattr(agent, 'evolution_engine')
        assert hasattr(agent, 'task_history')
        print("✅ All required attributes present")
        
        return True
    except Exception as e:
        print(f"❌ Instantiation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_abstract_method():
    """Test that abstract method is properly implemented."""
    print("\n🔍 Testing abstract method implementation...")
    try:
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )
        
        # Test method exists
        assert hasattr(agent, '_execute_specific_task')
        print("✅ _execute_specific_task method exists")
        
        # Test method is callable
        assert callable(agent._execute_specific_task)
        print("✅ Method is callable")
        
        # Test method is async
        import inspect
        assert inspect.iscoroutinefunction(agent._execute_specific_task)
        print("✅ Method is async")
        
        # Test method signature
        sig = inspect.signature(agent._execute_specific_task)
        params = list(sig.parameters.keys())
        expected_params = ['task', 'context']
        assert params == expected_params
        print("✅ Method signature is correct")
        
        return True
    except Exception as e:
        print(f"❌ Abstract method test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_zero_integration():
    """Test ZeroSystem integration."""
    print("\n🔍 Testing ZeroSystem integration...")
    try:
        from zero import ZeroSystem
        
        # Test creation
        system = ZeroSystem()
        print("✅ ZeroSystem created successfully")
        
        # Test initialization
        await system.initialize()
        print("✅ ZeroSystem initialized successfully")
        
        # Test evolution agent
        assert hasattr(system, 'evolution_agent')
        assert system.evolution_agent is not None
        print("✅ EvolutionaryAgent integrated successfully")
        
        # Test shutdown
        await system.shutdown()
        print("✅ ZeroSystem shutdown completed")
        
        return True
    except Exception as e:
        print(f"❌ Zero integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all validation tests."""
    print("🚀 COMPREHENSIVE EVOLUTIONARY AGENT VALIDATION")
    print("=" * 60)
    
    tests = [
        ("Import Tests", test_imports),
        ("Instantiation Tests", test_instantiation),
        ("Abstract Method Tests", test_abstract_method),
        ("Zero Integration Tests", test_zero_integration),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = await test_func()
            else:
                result = test_func()
            
            if result:
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print(f"\n{'='*60}")
    print(f"📊 FINAL RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL VALIDATION TESTS PASSED!")
        print("\n✅ EvolutionaryAgent fix is complete and working correctly:")
        print("  - All imports are working")
        print("  - Abstract method '_execute_specific_task' is implemented")
        print("  - Constructor signature is correct")
        print("  - ZeroSystem integration is working")
        print("  - No more 'Can't instantiate abstract class' errors")
        return True
    else:
        print("⚠️  Some validation tests failed. Please check the output above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)