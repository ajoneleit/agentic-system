#!/usr/bin/env python3
"""Trace Claude CLI calls to see exactly what's being executed."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.clients.claude_cli_client import ClaudeCLIClient


async def trace_cli_calls():
    """Trace CLI calls with detailed logging."""
    
    # Patch subprocess to log commands
    original_create_subprocess_exec = asyncio.create_subprocess_exec
    
    async def traced_subprocess(*args, **kwargs):
        print("\n🔍 SUBPROCESS CALL DETECTED:")
        print(f"   Command: {' '.join(str(arg) for arg in args)}")
        print(f"   Working dir: {Path.cwd()}")
        
        # Call the original
        result = await original_create_subprocess_exec(*args, **kwargs)
        return result
    
    # Apply the patch
    asyncio.create_subprocess_exec = traced_subprocess
    
    try:
        client = ClaudeCLIClient()
        
        print("=== Claude CLI Call Tracer ===\n")
        
        # Test 1: Check availability
        print("1. Testing CLI availability check...")
        available = await client.check_cli_available()
        print(f"   Result: {'Available' if available else 'Not available'}")
        
        if not available:
            print("\n❌ Claude CLI not found in PATH")
            print("   Install with: pip install claude-cli")
            return
        
        # Test 2: Simple code generation
        print("\n2. Testing code generation...")
        prompt = "Write a Python function that returns 'Hello, World!'"
        print(f"   Prompt: {prompt}")
        
        response = await client.create_code(
            prompt=prompt,
            temperature=0.3,
            max_tokens=200
        )
        
        print(f"\n   Response length: {len(response)} characters")
        print("   First 100 chars:", response[:100] + "..." if len(response) > 100 else response)
        
        # Test 3: Code with context files
        print("\n3. Testing with context files...")
        
        # Create a temporary context file
        context_file = Path("/tmp/context_example.py")
        context_file.write_text("""
# Example context file
class Calculator:
    def add(self, a, b):
        return a + b
""")
        
        prompt_with_context = "Add a subtract method to the Calculator class"
        print(f"   Prompt: {prompt_with_context}")
        print(f"   Context file: {context_file}")
        
        response = await client.create_code(
            prompt=prompt_with_context,
            context_files=[context_file],
            temperature=0.3
        )
        
        print(f"\n   Response length: {len(response)} characters")
        
        await client.close()
        
    finally:
        # Restore original
        asyncio.create_subprocess_exec = original_create_subprocess_exec
        
    print("\n✅ Tracing complete!")


async def test_raw_cli():
    """Test raw CLI command to verify it works."""
    print("=== Testing Raw Claude CLI Command ===\n")
    
    cmd = ["claude", "--print", "Write a simple Python hello world function"]
    print(f"Executing: {' '.join(cmd)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            print("\n✅ Success!")
            print("Output:")
            print("-" * 50)
            print(stdout.decode('utf-8'))
            print("-" * 50)
        else:
            print(f"\n❌ Failed with return code: {process.returncode}")
            print("Error:", stderr.decode('utf-8'))
            
    except FileNotFoundError:
        print("❌ 'claude' command not found in PATH")
        print("   Make sure Claude CLI is installed: pip install claude-cli")
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run tracing tests."""
    print("Choose test:")
    print("1. Trace CLI calls through the client")
    print("2. Test raw CLI command directly")
    print("3. Run both")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == "1":
        await trace_cli_calls()
    elif choice == "2":
        await test_raw_cli()
    elif choice == "3":
        await trace_cli_calls()
        print("\n" + "="*60 + "\n")
        await test_raw_cli()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())