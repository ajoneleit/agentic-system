#!/usr/bin/env python3
"""Interactive test for Claude CLI - use in Python REPL."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from src.clients.claude_cli_client import ClaudeCLIClient


def test_cli_sync():
    """Synchronous wrapper for testing in REPL."""
    
    async def _test():
        client = ClaudeCLIClient()
        
        # Check if CLI is available
        print("Checking CLI availability...")
        available = await client.check_cli_available()
        if not available:
            print("❌ Claude CLI not available")
            return None
            
        print("✅ Claude CLI is available!")
        
        # Get user prompt
        prompt = input("\nEnter your prompt (or 'exit' to quit): ")
        if prompt.lower() == 'exit':
            return None
            
        print("\nCalling Claude CLI...")
        print("Command being executed: claude --print \"<your prompt>\"")
        print("\nWaiting for response...\n")
        
        try:
            response = await client.create_code(prompt=prompt)
            print("Response:")
            print("="*60)
            print(response)
            print("="*60)
            return response
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            await client.close()
    
    return asyncio.run(_test())


# For REPL usage
print("""
Claude CLI Interactive Test
===========================

To test the CLI, you can:

1. Run the test function:
   >>> result = test_cli_sync()

2. Or test manually:
   >>> import asyncio
   >>> from src.clients.claude_cli_client import ClaudeCLIClient
   >>> 
   >>> async def test():
   ...     client = ClaudeCLIClient()
   ...     available = await client.check_cli_available()
   ...     print(f"CLI available: {available}")
   ...     if available:
   ...         response = await client.create_code("Write a hello world function")
   ...         print(response)
   ...     await client.close()
   ...
   >>> asyncio.run(test())

3. To see the actual CLI command being executed, check the logs or add print statements.
""")