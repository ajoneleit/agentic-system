#!/usr/bin/env python3
"""Debug script to identify the artifacts attribute error."""

import asyncio
import sys
from pathlib import Path

# Add the project directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console

from zero import ZeroSystem

console = Console()

async def debug_artifacts_error():
    """Debug the artifacts attribute error."""
    console.print("[bold blue]🐛 Debugging Artifacts Error[/bold blue]")
    console.print("=" * 50)

    try:
        # Create system
        system = ZeroSystem()
        await system.initialize()

        console.print("✅ System initialized successfully")

        # Try to execute a simple task that should trigger the error
        console.print("🔄 Running task that should trigger the error...")

        result = await system.run_single_task("Create hello world script")

        console.print(f"Task result: {result}")

    except Exception as e:
        console.print(f"[red]❌ Error caught: {e}[/red]")
        import traceback
        traceback.print_exc()

        # Let's try to get more specific information
        console.print("\n[bold yellow]Analyzing the error...[/bold yellow]")

        # Check if the error is about artifacts
        if "'Result' object has no attribute 'artifacts'" in str(e):
            console.print("✅ Confirmed: This is the artifacts error")

        else:
            console.print("❓ Different error encountered")

    finally:
        if 'system' in locals():
            await system.shutdown()

if __name__ == "__main__":
    asyncio.run(debug_artifacts_error())
