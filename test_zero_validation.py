#!/usr/bin/env python3
"""Test zero.py integration with EvolutionaryAgent."""

import sys
import asyncio
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

async def test_zero_system():
    """Test that ZeroSystem can initialize with EvolutionaryAgent."""
    try:
        print("🔍 Testing ZeroSystem initialization...")
        
        # Test import
        from zero import ZeroSystem
        print("✅ ZeroSystem imported successfully")
        
        # Test initialization
        system = ZeroSystem()
        print("✅ ZeroSystem instantiated successfully")
        
        # Test system initialization
        await system.initialize()
        print("✅ ZeroSystem initialized successfully")
        
        # Test that evolution agent was created
        assert hasattr(system, 'evolution_agent')
        assert system.evolution_agent is not None
        print("✅ EvolutionaryAgent created and assigned")
        
        # Test shutdown
        await system.shutdown()
        print("✅ ZeroSystem shutdown completed")
        
        print("\n🎉 ALL TESTS PASSED! ZeroSystem integration is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_zero_system())
    sys.exit(0 if success else 1)