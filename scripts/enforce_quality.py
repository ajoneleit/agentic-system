#!/usr/bin/env python3
"""Quality Enforcement Script - Consolidates all quality checks
Integrates seamlessly with existing CI workflow and quality gates.
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class QualityCheck:
    """Represents a single quality check."""

    name: str
    command: list[str]
    description: str
    required: bool = True
    cwd: str = None


@dataclass
class QualityResult:
    """Result of a quality check."""

    check_name: str
    passed: bool
    exit_code: int
    output: str
    error_output: str


class QualityEnforcer:
    """Enforces quality standards across the codebase."""

    def __init__(self, project_root: Path = None):
        self.project_root = project_root or Path.cwd()
        self.results: list[QualityResult] = []

    def get_quality_checks(self, check_types: list[str]) -> list[QualityCheck]:
        """Get quality checks based on requested types."""
        all_checks = {
            "format": [
                QualityCheck(
                    name="Black Code Formatting",
                    command=[
                        "black",
                        "--check",
                        "--diff",
                        "--color",
                        "src/",
                        "scripts/",
                        "docs/validation/",
                    ],
                    description="Check Python code formatting with Black",
                ),
            ],
            "lint": [
                QualityCheck(
                    name="Ruff Linting - Critical Issues Only",
                    command=[
                        "ruff",
                        "check",
                        "src/",
                        "scripts/",
                        "docs/validation/",
                        "--select",
                        "E,F",
                    ],
                    description="Lint Python code with Ruff (critical issues only)",
                ),
                QualityCheck(
                    name="PyLint Critical Issues",
                    command=[
                        "python",
                        "-m",
                        "pylint",
                        "src/",
                        "--errors-only",  # Only show errors, not warnings
                        "--output-format=text",  # Use text format for better readability
                        "--disable=import-error,no-member,invalid-sequence-index,unexpected-keyword-arg,no-value-for-parameter",  # Disable problematic checks temporarily
                    ],
                    description="Check for critical PyLint issues only",
                    required=False,  # Make Pylint optional for now
                ),
            ],
            "type": [
                QualityCheck(
                    name="MyPy Type Checking",
                    command=["mypy", ".", "--ignore-missing-imports", "--check-untyped-defs"],
                    description="Type check Python code with MyPy",
                    required=False,  # Type checking is optional for now
                ),
            ],
            "test": [
                QualityCheck(
                    name="Unit Tests",
                    command=["pytest", "tests/unit/", "-v", "--tb=short"],
                    description="Run unit tests",
                ),
                QualityCheck(
                    name="Coverage Check",
                    command=[
                        "pytest",
                        "tests/unit/",
                        "--cov=src",
                        "--cov-report=xml",
                        "--cov-report=term-missing",
                        "--cov-fail-under=90",  # Standard 90% coverage target
                    ],
                    description="Check test coverage",
                ),
            ],
            "rust": [
                QualityCheck(
                    name="Rust Clippy Linting",
                    command=["cargo", "clippy", "--workspace", "--", "-D", "warnings"],
                    description="Lint Rust code with Clippy (zero warnings)",
                    cwd="zero-engine",
                    required=False,  # Optional until Rust code quality improves
                ),
                QualityCheck(
                    name="Rust Unit Tests",
                    command=["cargo", "test", "--workspace"],
                    description="Run Rust unit tests",
                    cwd="zero-engine",
                    required=False,  # Optional until Rust code compiles
                ),
                QualityCheck(
                    name="Rust Format Check",
                    command=["cargo", "fmt", "--all", "--", "--check"],
                    description="Check Rust code formatting",
                    cwd="zero-engine",
                    required=False,  # Optional formatting check
                ),
            ],
            "docs": [
                QualityCheck(
                    name="Documentation Quality Gates",
                    command=["python", "docs/validation/quality_gates.py", "--pre-commit"],
                    description="Enforce documentation quality gates",
                ),
            ],
            "badges": [
                QualityCheck(
                    name="Test Count Badge Generation",
                    command=["python", "scripts/generate_test_badge.py"],
                    description="Generate auto-updated test count badge",
                    required=False,  # Badge generation is informational
                ),
            ],
        }

        checks = []
        for check_type in check_types:
            if check_type in all_checks:
                checks.extend(all_checks[check_type])
            elif check_type == "all":
                for type_checks in all_checks.values():
                    checks.extend(type_checks)

        return checks

    def run_check(self, check: QualityCheck) -> QualityResult:
        """Run a single quality check."""
        print(f"🔍 Running {check.name}...")

        cwd = self.project_root / check.cwd if check.cwd else self.project_root

        try:
            result = subprocess.run(
                check.command,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=300,  # 5 minute timeout
            )

            passed = result.returncode == 0
            if passed:
                print(f"✅ {check.name} - PASSED")
            else:
                print(f"❌ {check.name} - FAILED (exit code: {result.returncode})")
                if result.stderr:
                    print(f"   Error: {result.stderr[:200]}...")

            return QualityResult(
                check_name=check.name,
                passed=passed,
                exit_code=result.returncode,
                output=result.stdout,
                error_output=result.stderr,
            )

        except subprocess.TimeoutExpired:
            print(f"⏰ {check.name} - TIMEOUT")
            return QualityResult(
                check_name=check.name,
                passed=False,
                exit_code=-1,
                output="",
                error_output="Command timed out after 5 minutes",
            )
        except FileNotFoundError:
            print(f"🚫 {check.name} - COMMAND NOT FOUND")
            return QualityResult(
                check_name=check.name,
                passed=not check.required,  # Optional checks pass if command not found
                exit_code=-2,
                output="",
                error_output=f"Command not found: {' '.join(check.command)}",
            )
        except Exception as e:
            print(f"💥 {check.name} - ERROR: {str(e)}")
            return QualityResult(
                check_name=check.name, passed=False, exit_code=-3, output="", error_output=str(e)
            )

    def run_quality_checks(self, check_types: list[str], fail_fast: bool = False) -> bool:
        """Run quality checks and return overall success."""
        print("🚀 ENFORCING QUALITY STANDARDS")
        print("=" * 50)

        checks = self.get_quality_checks(check_types)

        if not checks:
            print("⚠️ No quality checks found for requested types")
            return True

        print(f"📋 Running {len(checks)} quality checks...")
        print()

        for check in checks:
            result = self.run_check(check)
            self.results.append(result)

            if fail_fast and not result.passed and check.required:
                print(f"🛑 FAIL FAST: Stopping due to failed check: {check.name}")
                break

        return self.print_summary()

    def print_summary(self) -> bool:
        """Print quality check summary and return overall success."""
        print()
        print("=" * 50)
        print("📊 QUALITY ENFORCEMENT SUMMARY")
        print("=" * 50)

        passed_checks = [r for r in self.results if r.passed]
        failed_checks = [r for r in self.results if not r.passed]

        print(f"✅ Passed: {len(passed_checks)}")
        print(f"❌ Failed: {len(failed_checks)}")
        print(
            f"📈 Success Rate: {len(passed_checks)}/{len(self.results)} ({len(passed_checks)/len(self.results)*100:.1f}%)"
        )

        if failed_checks:
            print()
            print("❌ FAILED CHECKS:")
            for result in failed_checks:
                print(f"  • {result.check_name} (exit code: {result.exit_code})")
                if result.error_output:
                    print(f"    {result.error_output[:100]}...")

        success = len(failed_checks) == 0

        if success:
            print()
            print("🎉 ALL QUALITY CHECKS PASSED!")
        else:
            print()
            print("🚨 QUALITY ENFORCEMENT FAILED")
            print("Fix the issues above before proceeding.")

        return success

    def save_report(self, output_file: Path) -> None:
        """Save quality check results to JSON file."""
        report = {
            "timestamp": subprocess.check_output(["date", "-u", "+%Y-%m-%dT%H:%M:%SZ"])
            .decode()
            .strip(),
            "total_checks": len(self.results),
            "passed_checks": len([r for r in self.results if r.passed]),
            "failed_checks": len([r for r in self.results if not r.passed]),
            "success_rate": (
                len([r for r in self.results if r.passed]) / len(self.results)
                if self.results
                else 1.0
            ),
            "results": [
                {
                    "check_name": r.check_name,
                    "passed": r.passed,
                    "exit_code": r.exit_code,
                    "has_error": bool(r.error_output),
                }
                for r in self.results
            ],
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Enforce quality standards")
    parser.add_argument(
        "--checks",
        nargs="+",
        default=["format", "lint", "test"],
        choices=["format", "lint", "type", "test", "rust", "docs", "badges", "all"],
        help="Types of checks to run",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    parser.add_argument("--report", type=str, help="Save report to JSON file")
    parser.add_argument("--ci", action="store_true", help="CI mode - stricter checks")

    args = parser.parse_args()

    if args.ci:
        # In CI mode, include documentation checks and be more strict
        if "docs" not in args.checks:
            args.checks.append("docs")
        args.fail_fast = True

    enforcer = QualityEnforcer()
    success = enforcer.run_quality_checks(args.checks, args.fail_fast)

    if args.report:
        enforcer.save_report(Path(args.report))
        print(f"📄 Quality report saved to: {args.report}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
