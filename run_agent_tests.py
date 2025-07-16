#!/usr/bin/env python3
"""Run agent-related tests to verify the fix."""

import subprocess
import sys
from pathlib import Path

def run_pytest_tests():
    """Run pytest tests for agents."""
    try:
        print("🔍 Running agent tests with pytest...")
        
        # Run agent tests specifically
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_agents.py", "-v"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        
        print("📄 Test output:")
        print(result.stdout)
        if result.stderr:
            print("Errors:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ Agent tests passed")
            return True
        else:
            print(f"❌ Agent tests failed with exit code {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False

def run_integration_tests():
    """Run integration tests if they exist."""
    try:
        print("\n🔍 Running integration tests...")
        
        # Check if integration tests exist
        integration_path = Path("tests/integration")
        if not integration_path.exists():
            print("ℹ️  No integration tests found")
            return True
        
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/integration/", "-v"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent
        )
        
        print("📄 Integration test output:")
        print(result.stdout)
        if result.stderr:
            print("Errors:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("✅ Integration tests passed")
            return True
        else:
            print(f"❌ Integration tests failed with exit code {result.returncode}")
            return False
            
    except Exception as e:
        print(f"❌ Error running integration tests: {e}")
        return False

def main():
    """Run all relevant tests."""
    print("🚀 Running Agent Tests to Verify Fix...")
    print("=" * 50)
    
    tests = [
        ("Agent Tests", run_pytest_tests),
        ("Integration Tests", run_integration_tests),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
    
    print(f"\n📊 Results: {passed}/{total} test suites passed")
    
    if passed == total:
        print("🎉 All agent tests passed!")
        return True
    else:
        print("⚠️  Some tests failed. Check output above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)