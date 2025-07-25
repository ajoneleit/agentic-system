#!/usr/bin/env python3
"""Comprehensive verification of the MetaAgent initialization fix."""

import asyncio
import subprocess
import sys
from pathlib import Path


def test_zero_help():
    """Test that zero.py --help works without errors."""
    try:
        print("🔍 Testing zero.py --help...")

        result = subprocess.run(
            [sys.executable, "zero.py", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=Path(__file__).parent
        )

        if result.returncode == 0:
            print("✅ zero.py --help executed successfully")
            return True
        else:
            print(f"❌ zero.py --help failed with exit code {result.returncode}")
            print(f"STDERR: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error running zero.py --help: {e}")
        return False

async def test_meta_agent_direct():
    """Test MetaAgent initialization directly."""
    try:
        print("🔍 Testing MetaAgent initialization directly...")

        # Test direct MetaAgent import and initialization
        from pathlib import Path

        from src.agents.meta_agent import MetaAgent

        # Create MetaAgent with only the correct parameter
        meta_agent = MetaAgent(artifact_storage_path=Path("./projects"))
        print("✅ MetaAgent created successfully with artifact_storage_path")

        # Test that it has the expected attributes
        assert hasattr(meta_agent, 'ai_client')
        assert hasattr(meta_agent, 'task_manager')
        assert hasattr(meta_agent, 'coordinator')
        assert hasattr(meta_agent, 'artifact_manager')
        print("✅ MetaAgent has all expected attributes")

        # Test shutdown
        await meta_agent.shutdown()
        print("✅ MetaAgent shutdown completed")

        return True

    except Exception as e:
        print(f"❌ Error testing MetaAgent directly: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_zero_system():
    """Test ZeroSystem initialization."""
    try:
        print("🔍 Testing ZeroSystem initialization...")

        from zero import ZeroSystem

        # Create ZeroSystem instance
        system = ZeroSystem()
        print("✅ ZeroSystem instance created successfully")

        # Test initialization
        await system.initialize()
        print("✅ ZeroSystem initialized successfully")

        # Test shutdown
        await system.shutdown()
        print("✅ ZeroSystem shutdown completed")

        return True

    except Exception as e:
        print(f"❌ Error during ZeroSystem test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    print("🚀 Verifying MetaAgent initialization fix...")
    print("=" * 60)

    tests = [
        ("Zero Help Command", test_zero_help),
        ("MetaAgent Direct Test", test_meta_agent_direct),
        ("ZeroSystem Test", test_zero_system),
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
        print("🎉 ALL TESTS PASSED! MetaAgent initialization fix is working correctly.")
        print("\nThe issue has been resolved:")
        print("- Removed 'use_cli_for_subagents' parameter from MetaAgent constructor")
        print("- MetaAgent now initializes with only 'artifact_storage_path' parameter")
        print("- Sub-agents will automatically pick up CLI configuration from settings")
        return True
    else:
        print("⚠️  Some tests failed. Please check the output above.")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
