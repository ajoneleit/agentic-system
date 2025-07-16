#!/usr/bin/env python3
"""Test zero.py help command"""

import subprocess
import sys

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
            print("\n📄 Help output:")
            print("-" * 50)
            print(result.stdout)
            print("-" * 50)
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

if __name__ == "__main__":
    success = test_zero_help()
    sys.exit(0 if success else 1)