#!/usr/bin/env python3
"""Run all tests for zero.py"""

import os
import subprocess
import sys


def run_test(test_file, description):
    """Run a test file and return success status."""
    print(f"\n🔍 Running {description}...")
    print("=" * 50)

    try:
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            timeout=60
        )

        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)

        if result.returncode == 0:
            print(f"✅ {description} PASSED")
            return True
        else:
            print(f"❌ {description} FAILED (exit code: {result.returncode})")
            return False

    except subprocess.TimeoutExpired:
        print(f"❌ {description} TIMED OUT")
        return False
    except Exception as e:
        print(f"❌ Error running {description}: {e}")
        return False

def main():
    """Run all tests."""
    print("🚀 Running Zero.py Test Suite")
    print("=" * 50)

    tests = [
        ("test_all_imports.py", "Import Tests"),
        ("test_zero_help.py", "Zero.py Help Command"),
    ]

    passed = 0
    total = len(tests)

    for test_file, description in tests:
        if os.path.exists(test_file):
            if run_test(test_file, description):
                passed += 1
        else:
            print(f"❌ Test file {test_file} not found")

    print(f"\n📊 Final Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! Zero.py is ready to use.")
        return 0
    else:
        print("⚠️  Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
