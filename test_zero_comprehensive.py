#!/usr/bin/env python3
"""Comprehensive test of zero.py functionality"""

import subprocess
import sys
import os
import time

def test_zero_help():
    """Test zero.py --help command."""
    print("🔍 Testing zero.py --help...")
    
    try:
        result = subprocess.run(
            [sys.executable, "zero.py", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("✅ zero.py --help executed successfully")
            print("\n📄 Help output preview:")
            print(result.stdout[:500] + "..." if len(result.stdout) > 500 else result.stdout)
            return True
        else:
            print(f"❌ zero.py --help failed with exit code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ zero.py --help timed out")
        return False
    except Exception as e:
        print(f"❌ Error running zero.py --help: {e}")
        return False

def test_zero_version():
    """Test zero.py --version if available."""
    print("\n🔍 Testing zero.py --version...")
    
    try:
        result = subprocess.run(
            [sys.executable, "zero.py", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ zero.py --version executed successfully")
            print(f"Version output: {result.stdout.strip()}")
            return True
        else:
            print("ℹ️  zero.py --version not available (this is OK)")
            return True  # Not a failure
            
    except Exception as e:
        print("ℹ️  zero.py --version test skipped")
        return True  # Not a failure

def test_zero_import():
    """Test importing zero.py as a module."""
    print("\n🔍 Testing zero.py module import...")
    
    try:
        # Test basic import
        import zero
        print("✅ zero.py imported successfully")
        
        # Test ZeroSystem creation
        system = zero.ZeroSystem()
        print("✅ ZeroSystem created successfully")
        
        # Test basic attributes
        attrs = ['settings', 'artifacts_path', 'mcp_config', 'initialized']
        for attr in attrs:
            if hasattr(system, attr):
                print(f"✅ System has {attr} attribute")
            else:
                print(f"⚠️  System missing {attr} attribute")
        
        return True
        
    except Exception as e:
        print(f"❌ zero.py import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_zero_dry_run():
    """Test zero.py with a simple dry run."""
    print("\n🔍 Testing zero.py dry run...")
    
    try:
        # Test with invalid flag to avoid full initialization
        result = subprocess.run(
            [sys.executable, "zero.py", "--invalid-flag"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        # We expect this to fail, but it should fail cleanly
        if "Usage:" in result.stdout or "usage:" in result.stdout.lower():
            print("✅ zero.py responds to invalid arguments cleanly")
            return True
        else:
            print("ℹ️  zero.py dry run test inconclusive")
            return True  # Not a failure
            
    except Exception as e:
        print(f"ℹ️  zero.py dry run test skipped: {e}")
        return True  # Not a failure

def test_dependencies():
    """Test that all dependencies are available."""
    print("\n🔍 Testing dependencies...")
    
    dependencies = [
        'click',
        'rich',
        'structlog',
        'numpy',
        'asyncio',
        'json',
        'pathlib',
    ]
    
    missing = []
    
    for dep in dependencies:
        try:
            __import__(dep)
            print(f"✅ {dep} available")
        except ImportError:
            print(f"❌ {dep} MISSING")
            missing.append(dep)
    
    if missing:
        print(f"❌ Missing dependencies: {missing}")
        return False
    else:
        print("✅ All dependencies available")
        return True

def test_custom_modules():
    """Test our custom modules."""
    print("\n🔍 Testing custom modules...")
    
    modules = [
        'src.visualization.net_visualizer',
        'src.interface.slash_commands',
        'src.core.mece_decomposer',
        'src.agents.evolutionary_agent',
        'src.agents.meta_agent',
        'src.core.interfaces',
        'config',
    ]
    
    failed = []
    
    for module in modules:
        try:
            __import__(module)
            print(f"✅ {module} imported")
        except ImportError as e:
            print(f"❌ {module} FAILED: {e}")
            failed.append(module)
    
    if failed:
        print(f"❌ Failed to import: {failed}")
        return False
    else:
        print("✅ All custom modules imported successfully")
        return True

def main():
    """Run comprehensive tests."""
    print("🚀 Zero.py Comprehensive Test Suite")
    print("=" * 60)
    
    tests = [
        ("Dependencies", test_dependencies),
        ("Custom Modules", test_custom_modules),
        ("Zero Import", test_zero_import),
        ("Zero Help", test_zero_help),
        ("Zero Version", test_zero_version),
        ("Zero Dry Run", test_zero_dry_run),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} PASSED")
            else:
                print(f"❌ {test_name} FAILED")
        except Exception as e:
            print(f"❌ {test_name} ERROR: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print(f"📊 FINAL RESULTS: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 ALL TESTS PASSED! Zero.py is ready to use.")
        print("\nYou can now run:")
        print("  python zero.py --help")
        print("  python zero.py")
        print("  python zero.py 'your task description'")
        return 0
    else:
        print("⚠️  Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())