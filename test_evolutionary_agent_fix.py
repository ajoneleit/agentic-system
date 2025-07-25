#!/usr/bin/env python3
"""Test script to verify EvolutionaryAgent instantiation fix."""

import asyncio
import sys
from pathlib import Path
from uuid import uuid4

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

async def test_evolutionary_agent_instantiation():
    """Test that EvolutionaryAgent can be instantiated without abstract method error."""
    try:
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole

        print("🔍 Testing EvolutionaryAgent instantiation...")

        # Test instantiation with required parameters
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )

        print("✅ EvolutionaryAgent instantiated successfully")

        # Test that it has the expected attributes
        assert hasattr(agent, 'memory')
        assert hasattr(agent, 'evolution_engine')
        assert hasattr(agent, 'evolution_enabled')
        assert hasattr(agent, 'task_history')
        print("✅ EvolutionaryAgent has all expected attributes")

        # Test that it has the required abstract method implemented
        assert hasattr(agent, '_execute_specific_task')
        print("✅ EvolutionaryAgent has _execute_specific_task method")

        # Test that the method is callable
        import inspect
        assert inspect.iscoroutinefunction(agent._execute_specific_task)
        print("✅ _execute_specific_task is an async method")

        return True

    except Exception as e:
        print(f"❌ EvolutionaryAgent instantiation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_zero_system_initialization():
    """Test that ZeroSystem can now initialize with EvolutionaryAgent."""
    try:
        from zero import ZeroSystem

        print("\n🔍 Testing ZeroSystem initialization with EvolutionaryAgent...")

        # Create ZeroSystem instance
        system = ZeroSystem()
        print("✅ ZeroSystem instance created successfully")

        # Test initialization (this should now work without abstract method error)
        await system.initialize()
        print("✅ ZeroSystem initialized successfully with EvolutionaryAgent")

        # Test that evolution agent was created
        assert hasattr(system, 'evolution_agent')
        assert system.evolution_agent is not None
        print("✅ EvolutionaryAgent was created and assigned to system")

        # Test shutdown
        await system.shutdown()
        print("✅ ZeroSystem shutdown completed")

        return True

    except Exception as e:
        print(f"❌ ZeroSystem initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_evolutionary_agent_method_signature():
    """Test that the _execute_specific_task method has the correct signature."""
    try:
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole

        print("\n🔍 Testing EvolutionaryAgent method signature...")

        # Create agent
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )

        # Get method signature
        import inspect
        sig = inspect.signature(agent._execute_specific_task)
        params = list(sig.parameters.keys())

        # Check parameters
        expected_params = ['task', 'context']
        assert params == expected_params, f"Expected {expected_params}, got {params}"
        print("✅ Method signature is correct")

        # Check return type annotation
        return_annotation = sig.return_annotation
        print(f"✅ Return annotation: {return_annotation}")

        return True

    except Exception as e:
        print(f"❌ Method signature test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing EvolutionaryAgent Abstract Method Fix...")
    print("=" * 60)

    tests = [
        ("EvolutionaryAgent Instantiation", test_evolutionary_agent_instantiation),
        ("Method Signature", test_evolutionary_agent_method_signature),
        ("ZeroSystem Initialization", test_zero_system_initialization),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")

        try:
            result = await test_func()

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
        print("🎉 ALL TESTS PASSED! EvolutionaryAgent abstract method fix is working correctly.")
        print("\nThe issue has been resolved:")
        print("- Implemented missing '_execute_specific_task' abstract method")
        print("- Fixed constructor to match SubAgent pattern")
        print("- Added proper error handling and Result types")
        print("- EvolutionaryAgent now instantiates successfully")
        return True
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
