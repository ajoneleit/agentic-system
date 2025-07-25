#!/usr/bin/env python3
"""Script to run all tests with proper configuration and reporting."""

import subprocess
import time
from pathlib import Path


def run_command(cmd, description):
    """Run a command and report results."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    start_time = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)  # 5 min timeout
        duration = time.time() - start_time

        print(f"Duration: {duration:.2f} seconds")
        print(f"Return code: {result.returncode}")

        if result.stdout:
            print("STDOUT:")
            print(result.stdout)

        if result.stderr:
            print("STDERR:")
            print(result.stderr)

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        print("TIMEOUT: Command took longer than 5 minutes")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def main():
    """Run all test configurations."""
    # Change to project directory
    project_root = Path(__file__).parent
    print(f"Project root: {project_root}")

    # Test configurations to try
    test_configs = [
        {
            "name": "Foundation Hardening Tests Only",
            "cmd": [
                "python", "-m", "pytest",
                "tests/test_orchestration_engine.py",
                "tests/test_artifact_store.py",
                "tests/test_repair_logic.py",
                "tests/test_claude_cli_integration.py",
                "tests/test_workspace_index.py",
                "-v", "--tb=short"
            ]
        },
        {
            "name": "Working Tests with Coverage",
            "cmd": [
                "python", "-m", "pytest",
                "tests/test_artifact_manager.py",
                "tests/test_claude_cli_client_robust.py",
                "tests/test_repair_logic.py",
                "tests/test_result_integration.py",
                "--cov=src", "--cov-report=term-missing",
                "-v", "--tb=short"
            ]
        },
        {
            "name": "All Tests in Parallel (Fast)",
            "cmd": [
                "python", "-m", "pytest",
                "tests/",
                "-n", "auto",  # Use all CPU cores
                "--dist=worksteal",
                "--tb=short",
                "--maxfail=10"  # Stop after 10 failures
            ]
        },
        {
            "name": "All Tests with Full Coverage Report",
            "cmd": [
                "python", "-m", "pytest",
                "tests/",
                "--cov=src",
                "--cov-report=html",
                "--cov-report=term-missing",
                "-x",  # Stop on first failure
                "--tb=short"
            ]
        }
    ]

    results = {}

    for config in test_configs:
        success = run_command(config["cmd"], config["name"])
        results[config["name"]] = success

        if not success:
            print(f"\n❌ {config['name']} FAILED")
        else:
            print(f"\n✅ {config['name']} PASSED")

        # Ask user if they want to continue after failures
        if not success and config["name"] != test_configs[-1]["name"]:
            response = input("\nContinue with next test configuration? (y/n): ")
            if response.lower() not in ['y', 'yes']:
                break

    # Final summary
    print(f"\n{'='*60}")
    print("FINAL RESULTS:")
    print(f"{'='*60}")

    for name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} - {name}")

    # Check if coverage report was generated
    coverage_html = project_root / "htmlcov" / "index.html"
    if coverage_html.exists():
        print(f"\n📊 Coverage report generated: {coverage_html}")
        print("Open this file in your browser to view detailed coverage")

if __name__ == "__main__":
    main()
