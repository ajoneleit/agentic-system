#!/usr/bin/env python3
"""Test all imports needed for zero.py"""

import sys
import traceback

def test_imports():
    """Test all the imports that zero.py needs."""
    
    tests = [
        ("Standard library imports", lambda: __import__('asyncio')),
        ("External library imports", lambda: __import__('click')),
        ("Rich imports", lambda: __import__('rich.console')),
        ("Structlog", lambda: __import__('structlog')),
        ("Config import", lambda: __import__('config')),
        ("Evolutionary agent", lambda: __import__('src.agents.evolutionary_agent')),
        ("Meta agent", lambda: __import__('src.agents.meta_agent')),
        ("Core interfaces", lambda: __import__('src.core.interfaces')),
        ("Slash commands", lambda: __import__('src.interface.slash_commands')),
        ("Visualization", lambda: __import__('src.visualization.net_visualizer')),
        ("MECE decomposer", lambda: __import__('src.core.mece_decomposer')),
    ]
    
    passed = 0
    failed = []
    
    for test_name, test_func in tests:
        try:
            test_func()
            print(f"✅ {test_name}: OK")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name}: FAILED - {e}")
            failed.append((test_name, str(e)))
    
    print(f"\n📊 Results: {passed}/{len(tests)} imports successful")
    
    if failed:
        print("\n❌ Failed imports:")
        for name, error in failed:
            print(f"  - {name}: {error}")
        return False
    else:
        print("🎉 All imports successful!")
        return True

def test_zero_import():
    """Test importing zero.py specifically."""
    print("\n🔍 Testing zero.py import...")
    try:
        import zero
        print("✅ zero.py import successful")
        
        # Test ZeroSystem creation
        system = zero.ZeroSystem()
        print("✅ ZeroSystem creation successful")
        
        return True
    except Exception as e:
        print(f"❌ zero.py import failed: {e}")
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Testing All Imports for Zero.py")
    print("=" * 50)
    
    success1 = test_imports()
    success2 = test_zero_import()
    
    if success1 and success2:
        print("\n🎉 All tests passed! Zero.py should work.")
        sys.exit(0)
    else:
        print("\n⚠️  Some tests failed. Check output above.")
        sys.exit(1)