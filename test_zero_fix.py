#!/usr/bin/env python3
"""Test script to verify the MetaAgent initialization fix."""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

async def test_zero_initialization():
    """Test that ZeroSystem can initialize without errors."""
    try:
        from zero import ZeroSystem
        
        print("🔍 Testing ZeroSystem initialization...")
        
        # Create ZeroSystem instance
        system = ZeroSystem()
        print("✅ ZeroSystem instance created successfully")
        
        # Test initialization
        await system.initialize()
        print("✅ ZeroSystem initialized successfully")
        
        # Test shutdown
        await system.shutdown()
        print("✅ ZeroSystem shutdown completed")
        
        print("\n🎉 All tests passed! The MetaAgent parameter mismatch is fixed.")
        return True
        
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_zero_initialization())
    sys.exit(0 if success else 1)