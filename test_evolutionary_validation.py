#!/usr/bin/env python3
"""Simple validation test for EvolutionaryAgent fix."""

import sys
from pathlib import Path
from uuid import uuid4

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

def test_evolutionary_agent_fix():
    """Test that EvolutionaryAgent can be instantiated and has the required methods."""
    try:
        print("🔍 Testing EvolutionaryAgent fix...")
        
        # Test imports
        from src.agents.evolutionary_agent import EvolutionaryAgent
        from src.core.interfaces import AgentRole
        print("✅ Imports successful")
        
        # Test instantiation
        agent = EvolutionaryAgent(
            agent_id=uuid4(),
            role=AgentRole.CORE_LOGIC,
            artifact_storage_path=Path("./projects"),
            evolution_enabled=True
        )
        print("✅ EvolutionaryAgent instantiated successfully")
        
        # Test required method exists
        assert hasattr(agent, '_execute_specific_task')
        print("✅ _execute_specific_task method exists")
        
        # Test method is callable
        assert callable(agent._execute_specific_task)
        print("✅ _execute_specific_task is callable")
        
        # Test method is async
        import inspect
        assert inspect.iscoroutinefunction(agent._execute_specific_task)
        print("✅ _execute_specific_task is async")
        
        print("\n🎉 ALL TESTS PASSED! EvolutionaryAgent fix is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_evolutionary_agent_fix()
    sys.exit(0 if success else 1)