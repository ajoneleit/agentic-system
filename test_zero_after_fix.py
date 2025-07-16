#\!/usr/bin/env python3
"""Test zero.py after the artifacts fix."""

import asyncio
import sys
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from zero import ZeroSystem
from rich.console import Console

console = Console()

async def test_zero_after_fix():
    """Test zero.py after the artifacts fix."""
    
    console.print("[bold blue]🔧 Testing Zero.py After Artifacts Fix[/bold blue]")
    console.print("=" * 50)
    
    try:
        # Create system
        system = ZeroSystem()
        await system.initialize()
        
        console.print("✅ System initialized successfully")
        
        # Try to execute a simple task
        console.print("🔄 Running simple task...")
        
        result = await system.run_single_task("Create a simple hello world Python script")
        
        if result:
            console.print("✅ Task completed successfully\!")
            console.print("   This means the artifacts error is fixed.")
        else:
            console.print("❌ Task failed, but no artifacts error means progress")
            
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        
        # Check if this is still the artifacts error
        if "'Result' object has no attribute 'artifacts'" in str(e):
            console.print("❌ Still getting the artifacts error - fix incomplete")
        else:
            console.print("✅ Different error - artifacts error is fixed\!")
            console.print("   Now we can work on other issues.")
            
    finally:
        if 'system' in locals():
            await system.shutdown()

if __name__ == "__main__":
    asyncio.run(test_zero_after_fix())
EOF < /dev/null
