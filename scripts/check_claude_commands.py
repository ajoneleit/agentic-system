#!/usr/bin/env python3
"""Check what Claude commands are actually available."""

import subprocess


def run_command(cmd, description):
    """Run a command and show results."""
    print(f"\n{description}")
    print("-" * 50)
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        print(f"Return code: {result.returncode}")
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        if result.stderr:
            print("STDERR:")
            print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("Command timed out")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    """Check Claude commands."""
    print("CHECKING CLAUDE COMMANDS")
    print("=" * 50)

    commands = [
        ("claude --version", "Check Claude version"),
        ("claude --help", "Check Claude help"),
        ("claude chat --help", "Check if 'chat' subcommand exists"),
        ("claude code --help", "Check if 'code' subcommand exists"),
        ("which claude", "Find Claude location"),
        ("ls -la $(which claude)", "Check Claude binary details"),
    ]

    for cmd, desc in commands:
        run_command(cmd, desc)


if __name__ == "__main__":
    main()
