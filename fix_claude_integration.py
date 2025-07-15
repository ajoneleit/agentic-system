#!/usr/bin/env python3
"""Fix Claude integration to work with Claude Code instead of Claude CLI."""

import subprocess
import sys

def check_claude_code_commands():
    """Check what commands Claude Code actually supports."""
    print("CHECKING CLAUDE CODE COMMANDS")
    print("=" * 50)
    
    try:
        # Check version
        result = subprocess.run(['claude', '--version'], capture_output=True, text=True)
        print(f"Version: {result.stdout.strip()}")
        
        # Check help
        result = subprocess.run(['claude', '--help'], capture_output=True, text=True)
        print("\nAvailable commands:")
        lines = result.stdout.split('\n')
        in_commands = False
        for line in lines:
            if 'Commands:' in line:
                in_commands = True
                continue
            if in_commands and line.strip():
                if line.startswith('  '):
                    print(f"  {line.strip()}")
                else:
                    break
        
        # Test if 'chat' subcommand exists
        result = subprocess.run(['claude', 'chat', '--help'], capture_output=True, text=True)
        if result.returncode == 0:
            print("\n✅ 'chat' subcommand exists")
        else:
            print(f"\n❌ 'chat' subcommand does NOT exist")
            print(f"Error: {result.stderr}")
        
        # Test what the main command does
        print("\n" + "=" * 50)
        print("TESTING MAIN CLAUDE COMMAND")
        print("=" * 50)
        
        # Test direct usage
        test_input = "Write a simple hello world function in Python"
        result = subprocess.run(['claude'], input=test_input, capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            print("✅ Direct 'claude' command works")
            print(f"Response (first 200 chars): {result.stdout[:200]}...")
        else:
            print(f"❌ Direct 'claude' command failed")
            print(f"Error: {result.stderr}")
            
    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    check_claude_code_commands()