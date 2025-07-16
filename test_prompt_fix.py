#!/usr/bin/env python3
"""Quick test to verify the prompt fix works."""

import subprocess
import sys
import time
from pathlib import Path

def test_interactive_prompt():
    """Test that python zero.py --enable-monitoring doesn't hang."""
    
    print("🧪 Testing that zero.py --enable-monitoring doesn't hang...")
    
    # Start the process
    process = subprocess.Popen(
        [sys.executable, "zero.py", "--enable-monitoring"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path(__file__).parent
    )
    
    try:
        # Give it a few seconds to initialize
        time.sleep(5)
        
        # Check if it's still running and responsive
        if process.poll() is None:
            print("✅ Process is running (not hanging)")
            
            # Send "exit" command to gracefully shutdown
            process.stdin.write("exit\n")
            process.stdin.flush()
            
            # Wait for shutdown
            try:
                stdout, stderr = process.communicate(timeout=10)
                print("✅ Process responded to exit command")
                return True
            except subprocess.TimeoutExpired:
                print("❌ Process didn't respond to exit command")
                process.kill()
                return False
        else:
            print("❌ Process exited unexpectedly")
            stdout, stderr = process.communicate()
            print(f"stdout: {stdout}")
            print(f"stderr: {stderr}")
            return False
            
    except Exception as e:
        print(f"❌ Test failed: {e}")
        process.kill()
        return False

if __name__ == "__main__":
    success = test_interactive_prompt()
    
    if success:
        print("\n🎉 Fix confirmed! python zero.py --enable-monitoring should work now.")
        print("Try running: python zero.py --enable-monitoring")
        print("You should see the prompt and be able to type normally.")
    else:
        print("\n❌ Fix validation failed. There may still be an issue.")
        
    sys.exit(0 if success else 1)