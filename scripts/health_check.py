#!/usr/bin/env python3
"""Run system health check for the Agentic Coding System."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.health_check import run_health_check_cli

if __name__ == "__main__":
    asyncio.run(run_health_check_cli())
