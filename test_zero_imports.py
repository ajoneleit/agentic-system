#!/usr/bin/env python3
"""Test script to verify zero.py imports work correctly."""

import sys
from pathlib import Path

def test_zero_imports():
    """Test that all zero.py imports work correctly."""
    try:
        # Test standard library imports
        import asyncio
        import json
        import sys
        from pathlib import Path
        from typing import Optional
        print("✅ Standard library imports: OK")
        
        # Test external library imports
        import click
        from rich.console import Console
        from rich.prompt import Prompt
        from rich.table import Table
        from rich.panel import Panel
        from rich.syntax import Syntax
        from structlog import get_logger
        print("✅ External library imports: OK")
        
        # Test internal imports
        from config import get_settings
        print("✅ Config import: OK")
        
        from src.agents.evolutionary_agent import EvolutionaryAgent
        print("✅ EvolutionaryAgent import: OK")
        
        from src.agents.meta_agent import MetaAgent
        print("✅ MetaAgent import: OK")
        
        from src.core.interfaces import AgentRole
        print("✅ AgentRole import: OK")
        
        from src.interface.slash_commands import ZeroInterface, CommandResult
        print("✅ ZeroInterface imports: OK")
        
        print("\n🎉 All imports successful! zero.py should run correctly.")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = test_zero_imports()
    sys.exit(0 if success else 1)