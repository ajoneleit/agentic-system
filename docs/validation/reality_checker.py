#!/usr/bin/env python3
"""Reality Checker - Validates system claims against actual implementation.

This module implements comprehensive reality checking to ensure all
documented features and claims match the actual system state.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil


@dataclass
class RealityCheck:
    """Result of a reality check."""

    check_name: str
    claimed_value: str
    actual_value: str
    passed: bool
    message: str
    timestamp: datetime
    details: dict[str, Any]


class RealityChecker:
    """Comprehensive reality checking system."""

    def __init__(self, project_root: Path = None):
        """Initialize reality checker."""
        self.project_root = project_root or Path.cwd()
        self.checks: list[RealityCheck] = []

    def check_all(self) -> list[RealityCheck]:
        """Run all reality checks."""
        self.checks.clear()

        # System architecture checks
        self._check_system_architecture()

        # Performance claims checks
        self._check_performance_claims()

        # Feature implementation checks
        self._check_feature_implementation()

        # Test coverage checks
        self._check_test_coverage()

        # Process implementation checks
        self._check_process_implementation()

        return self.checks

    def _check_system_architecture(self) -> None:
        """Verify system architecture claims."""
        # Check MetaAgent implementation
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from src.agents.meta_agent import MetaAgent; print('MetaAgent exists')",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            self.checks.append(
                RealityCheck(
                    check_name="MetaAgent Implementation",
                    claimed_value="MetaAgent orchestrates sub-agents",
                    actual_value=(
                        "MetaAgent class exists and importable"
                        if result.returncode == 0
                        else "MetaAgent import failed"
                    ),
                    passed=result.returncode == 0,
                    message="MetaAgent component verification",
                    timestamp=datetime.now(),
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        except Exception as e:
            self.checks.append(
                RealityCheck(
                    check_name="MetaAgent Implementation",
                    claimed_value="MetaAgent orchestrates sub-agents",
                    actual_value=f"Check failed: {str(e)}",
                    passed=False,
                    message="Failed to verify MetaAgent",
                    timestamp=datetime.now(),
                    details={"error": str(e)},
                )
            )

        # Check sub-agent implementation
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from src.agents.sub_agent import SubAgent; print('SubAgent exists')",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            self.checks.append(
                RealityCheck(
                    check_name="SubAgent Implementation",
                    claimed_value="Specialized sub-agents execute tasks",
                    actual_value=(
                        "SubAgent class exists and importable"
                        if result.returncode == 0
                        else "SubAgent import failed"
                    ),
                    passed=result.returncode == 0,
                    message="SubAgent component verification",
                    timestamp=datetime.now(),
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        except Exception as e:
            self.checks.append(
                RealityCheck(
                    check_name="SubAgent Implementation",
                    claimed_value="Specialized sub-agents execute tasks",
                    actual_value=f"Check failed: {str(e)}",
                    passed=False,
                    message="Failed to verify SubAgent",
                    timestamp=datetime.now(),
                    details={"error": str(e)},
                )
            )

    def _check_performance_claims(self) -> None:
        """Verify performance claims against actual measurements."""
        # Check health check performance claim: "< 2 seconds"
        start_time = time.time()
        try:
            result = subprocess.run(
                [sys.executable, "scripts/health_check.py"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
                timeout=10,
            )

            elapsed_time = time.time() - start_time

            self.checks.append(
                RealityCheck(
                    check_name="Health Check Performance",
                    claimed_value="< 2 seconds",
                    actual_value=f"{elapsed_time:.2f} seconds",
                    passed=elapsed_time < 2.0 and result.returncode == 0,
                    message="Health check execution time verification",
                    timestamp=datetime.now(),
                    details={
                        "elapsed_time": elapsed_time,
                        "return_code": result.returncode,
                        "stdout_length": len(result.stdout),
                    },
                )
            )
        except subprocess.TimeoutExpired:
            self.checks.append(
                RealityCheck(
                    check_name="Health Check Performance",
                    claimed_value="< 2 seconds",
                    actual_value="> 10 seconds (timeout)",
                    passed=False,
                    message="Health check timed out",
                    timestamp=datetime.now(),
                    details={"timeout": True},
                )
            )
        except Exception as e:
            self.checks.append(
                RealityCheck(
                    check_name="Health Check Performance",
                    claimed_value="< 2 seconds",
                    actual_value=f"Check failed: {str(e)}",
                    passed=False,
                    message="Failed to measure health check performance",
                    timestamp=datetime.now(),
                    details={"error": str(e)},
                )
            )

        # Check memory usage claim: "< 1GB peak for standard operations"
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            memory_gb = memory_mb / 1024

            self.checks.append(
                RealityCheck(
                    check_name="Memory Usage",
                    claimed_value="< 1GB peak for standard operations",
                    actual_value=f"{memory_gb:.2f} GB current usage",
                    passed=memory_gb < 1.0,
                    message="Memory usage verification",
                    timestamp=datetime.now(),
                    details={"memory_mb": memory_mb, "memory_gb": memory_gb},
                )
            )
        except Exception as e:
            self.checks.append(
                RealityCheck(
                    check_name="Memory Usage",
                    claimed_value="< 1GB peak for standard operations",
                    actual_value=f"Check failed: {str(e)}",
                    passed=False,
                    message="Failed to measure memory usage",
                    timestamp=datetime.now(),
                    details={"error": str(e)},
                )
            )

    def _check_feature_implementation(self) -> None:
        """Verify feature implementation claims."""
        # Check artifact management system
        artifacts_dir = self.project_root / "artifacts"

        self.checks.append(
            RealityCheck(
                check_name="Artifact Management System",
                claimed_value="Centralized storage with version control",
                actual_value=(
                    "Artifacts directory exists"
                    if artifacts_dir.exists()
                    else "Artifacts directory missing"
                ),
                passed=artifacts_dir.exists(),
                message="Artifact storage verification",
                timestamp=datetime.now(),
                details={"artifacts_path": str(artifacts_dir), "exists": artifacts_dir.exists()},
            )
        )

        # Check configuration system
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from config import get_settings; settings = get_settings(); print('Config loaded')",
                ],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )

            self.checks.append(
                RealityCheck(
                    check_name="Configuration System",
                    claimed_value="Configurable system settings",
                    actual_value=(
                        "Configuration system functional"
                        if result.returncode == 0
                        else "Configuration system failed"
                    ),
                    passed=result.returncode == 0,
                    message="Configuration system verification",
                    timestamp=datetime.now(),
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
            )
        except Exception as e:
            self.checks.append(
                RealityCheck(
                    check_name="Configuration System",
                    claimed_value="Configurable system settings",
                    actual_value=f"Check failed: {str(e)}",
                    passed=False,
                    message="Failed to verify configuration system",
                    timestamp=datetime.now(),
                    details={"error": str(e)},
                )
            )

    def _check_test_coverage(self) -> None:
        """Verify test coverage claims."""
        # Check for test files
        test_dirs = [
            self.project_root / "tests",
            self.project_root / "tests" / "unit",
            self.project_root / "tests" / "integration",
        ]

        total_test_files = 0
        for test_dir in test_dirs:
            if test_dir.exists():
                test_files = list(test_dir.glob("test_*.py"))
                total_test_files += len(test_files)

        # Check coverage data
        coverage_file = self.project_root / "coverage.xml"
        has_coverage_data = coverage_file.exists()

        self.checks.append(
            RealityCheck(
                check_name="Test Infrastructure",
                claimed_value="Comprehensive testing with coverage tracking",
                actual_value=f"{total_test_files} test files found, coverage data {'present' if has_coverage_data else 'missing'}",
                passed=total_test_files > 0,
                message="Test infrastructure verification",
                timestamp=datetime.now(),
                details={
                    "test_file_count": total_test_files,
                    "coverage_data_exists": has_coverage_data,
                },
            )
        )

    def _check_process_implementation(self) -> None:
        """Verify process implementation claims."""
        # Check CI pipeline
        ci_file = self.project_root / ".github" / "workflows" / "ci.yml"

        self.checks.append(
            RealityCheck(
                check_name="CI Pipeline",
                claimed_value="Comprehensive CI/CD pipeline",
                actual_value=(
                    "CI configuration exists" if ci_file.exists() else "CI configuration missing"
                ),
                passed=ci_file.exists(),
                message="CI pipeline verification",
                timestamp=datetime.now(),
                details={"ci_file": str(ci_file), "exists": ci_file.exists()},
            )
        )

        # Check health check script
        health_script = self.project_root / "scripts" / "health_check.py"

        self.checks.append(
            RealityCheck(
                check_name="Health Check Script",
                claimed_value="Automated system health validation",
                actual_value=(
                    "Health check script exists"
                    if health_script.exists()
                    else "Health check script missing"
                ),
                passed=health_script.exists(),
                message="Health check script verification",
                timestamp=datetime.now(),
                details={"script_path": str(health_script), "exists": health_script.exists()},
            )
        )

    def generate_reality_report(self) -> dict[str, Any]:
        """Generate comprehensive reality check report."""
        total_checks = len(self.checks)
        passed_checks = sum(1 for check in self.checks if check.passed)
        failed_checks = total_checks - passed_checks

        # Categorize failures
        critical_failures = []
        minor_failures = []

        for check in self.checks:
            if not check.passed:
                if "Performance" in check.check_name or "Implementation" in check.check_name:
                    critical_failures.append(check)
                else:
                    minor_failures.append(check)

        return {
            "summary": {
                "total_checks": total_checks,
                "passed": passed_checks,
                "failed": failed_checks,
                "success_rate": passed_checks / total_checks if total_checks > 0 else 1.0,
                "critical_failures": len(critical_failures),
                "minor_failures": len(minor_failures),
            },
            "critical_failures": [
                {
                    "check": failure.check_name,
                    "claimed": failure.claimed_value,
                    "actual": failure.actual_value,
                    "message": failure.message,
                }
                for failure in critical_failures
            ],
            "minor_failures": [
                {
                    "check": failure.check_name,
                    "claimed": failure.claimed_value,
                    "actual": failure.actual_value,
                    "message": failure.message,
                }
                for failure in minor_failures
            ],
            "all_checks": [
                {
                    "name": check.check_name,
                    "claimed": check.claimed_value,
                    "actual": check.actual_value,
                    "passed": check.passed,
                    "message": check.message,
                    "timestamp": check.timestamp.isoformat(),
                    "details": check.details,
                }
                for check in self.checks
            ],
        }

    def save_report(self, output_path: Path = None) -> None:
        """Save reality check report to file."""
        if output_path is None:
            output_path = self.project_root / "docs" / "metrics" / "reality-check.json"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        report = self.generate_reality_report()
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)


def main():
    """Main entry point for reality checking."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check system reality against documentation claims"
    )
    parser.add_argument(
        "--check-architecture", action="store_true", help="Check system architecture"
    )
    parser.add_argument("--check-performance", action="store_true", help="Check performance claims")
    parser.add_argument(
        "--check-features", action="store_true", help="Check feature implementation"
    )
    parser.add_argument("--check-all", action="store_true", help="Run all reality checks")
    parser.add_argument("--generate-report", action="store_true", help="Generate reality report")
    parser.add_argument("--save-report", type=str, help="Save report to specified file")
    parser.add_argument(
        "--fail-on-critical", action="store_true", help="Exit with error on critical failures"
    )

    args = parser.parse_args()

    checker = RealityChecker()

    if args.check_all or not any(
        [args.check_architecture, args.check_performance, args.check_features]
    ):
        checks = checker.check_all()
    else:
        if args.check_architecture:
            checker._check_system_architecture()
        if args.check_performance:
            checker._check_performance_claims()
        if args.check_features:
            checker._check_feature_implementation()
        checks = checker.checks

    # Print results
    passed = sum(1 for check in checks if check.passed)
    total = len(checks)

    print(f"Reality Check Results: {passed}/{total} passed")

    failed_checks = [check for check in checks if not check.passed]
    if failed_checks:
        print(f"\nFAILED CHECKS ({len(failed_checks)}):")
        for check in failed_checks:
            print(f"  ❌ {check.check_name}")
            print(f"     Claimed: {check.claimed_value}")
            print(f"     Actual: {check.actual_value}")
            print(f"     Message: {check.message}")
            print()

    if args.generate_report or args.save_report:
        report = checker.generate_reality_report()

        if args.generate_report:
            print(json.dumps(report, indent=2, default=str))

        if args.save_report:
            output_path = Path(args.save_report)
            checker.save_report(output_path)
            print(f"Report saved to: {output_path}")

    # Check for critical failures
    critical_failures = [
        check
        for check in failed_checks
        if "Performance" in check.check_name or "Implementation" in check.check_name
    ]

    if args.fail_on_critical and critical_failures:
        print(f"CRITICAL FAILURES DETECTED: {len(critical_failures)}")
        sys.exit(1)

    if failed_checks:
        sys.exit(1)


if __name__ == "__main__":
    main()
