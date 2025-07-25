#!/usr/bin/env python3
"""Quality Gates Enforcer - Implements Fail Fast, Fix Fast principle.

This module enforces quality gates and blocks deployment when standards drift.
Implements comprehensive validation with immediate failure feedback.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class GateStatus(Enum):
    """Quality gate status."""

    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    SKIP = "skip"


@dataclass
class GateResult:
    """Result of a quality gate check."""

    gate_name: str
    status: GateStatus
    message: str
    details: dict[str, Any]
    execution_time: float
    timestamp: datetime
    blocking: bool = True


class QualityGate:
    """Base class for quality gates."""

    def __init__(self, name: str, blocking: bool = True):
        self.name = name
        self.blocking = blocking

    def validate(self, project_root: Path) -> GateResult:
        """Validate the quality gate."""
        raise NotImplementedError("Subclasses must implement validate method")


class DocumentationRealityGate(QualityGate):
    """Gate 1: Documentation Reality Alignment."""

    def __init__(self):
        super().__init__("Documentation Reality Alignment", blocking=True)

    def validate(self, project_root: Path) -> GateResult:
        """Validate documentation reality alignment."""
        start_time = time.time()

        try:
            # Run documentation validator
            result = subprocess.run(
                [
                    sys.executable,
                    "docs/validation/doc_validator.py",
                    "--check-code-refs",
                    "--test-examples",
                    "--fail-fast",
                ],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=60,
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="All documentation claims verified against reality",
                    details={"stdout": result.stdout[:500]},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    message="Documentation claims do not match reality",
                    details={"stderr": result.stderr[:500], "stdout": result.stdout[:500]},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )

        except subprocess.TimeoutExpired:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message="Documentation validation timed out",
                details={"timeout": True},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Documentation validation failed: {str(e)}",
                details={"error": str(e)},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )


class CodeQualityGate(QualityGate):
    """Gate 2: Code Quality Standards."""

    def __init__(self):
        super().__init__("Code Quality Standards", blocking=True)

    def validate(self, project_root: Path) -> GateResult:
        """Validate code quality standards."""
        start_time = time.time()

        try:
            # Check formatting with Black
            black_result = subprocess.run(
                ["black", "--check", "."], capture_output=True, text=True, cwd=project_root
            )

            # Check linting with Ruff
            ruff_result = subprocess.run(
                ["ruff", "check", "."], capture_output=True, text=True, cwd=project_root
            )

            execution_time = time.time() - start_time

            issues = []
            if black_result.returncode != 0:
                issues.append("Code formatting issues detected")
            if ruff_result.returncode != 0:
                issues.append("Linting issues detected")

            if not issues:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="All code quality standards met",
                    details={"black_ok": True, "ruff_ok": True},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    message=f"Code quality issues: {', '.join(issues)}",
                    details={
                        "black_stderr": black_result.stderr[:300],
                        "ruff_stderr": ruff_result.stderr[:300],
                    },
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )

        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Code quality check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )


class SystemFunctionalityGate(QualityGate):
    """Gate 3: System Functionality."""

    def __init__(self):
        super().__init__("System Functionality", blocking=True)

    def validate(self, project_root: Path) -> GateResult:
        """Validate system functionality."""
        start_time = time.time()

        try:
            # Run health check
            health_result = subprocess.run(
                [sys.executable, "scripts/health_check.py"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=30,
            )

            # Test core imports
            import_result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    "from src.agents.meta_agent import MetaAgent; from src.agents.sub_agent import SubAgent; print('Core imports successful')",
                ],
                capture_output=True,
                text=True,
                cwd=project_root,
            )

            execution_time = time.time() - start_time

            issues = []
            if health_result.returncode != 0:
                issues.append("Health check failed")
            if import_result.returncode != 0:
                issues.append("Core imports failed")

            if not issues:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="All system functionality checks passed",
                    details={"health_ok": True, "imports_ok": True},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.FAIL,
                    message=f"System functionality issues: {', '.join(issues)}",
                    details={
                        "health_stderr": health_result.stderr[:300],
                        "import_stderr": import_result.stderr[:300],
                    },
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )

        except subprocess.TimeoutExpired:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message="System functionality check timed out",
                details={"timeout": True},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"System functionality check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )


class DocumentationCompletenessGate(QualityGate):
    """Gate 4: Documentation Completeness."""

    def __init__(self):
        super().__init__("Documentation Completeness", blocking=False)

    def validate(self, project_root: Path) -> GateResult:
        """Validate documentation completeness."""
        start_time = time.time()

        try:
            # Check required documentation files
            docs_root = project_root / "docs"
            required_files = [
                "index.md",
                "development/setup.md",
                "development/coding-standards.md",
                "processes/quality-gates.md",
                "validation/doc_validator.py",
                "validation/reality_checker.py",
                "validation/quality_gates.py",
            ]

            missing_files = []
            for req_file in required_files:
                if not (docs_root / req_file).exists():
                    missing_files.append(req_file)

            execution_time = time.time() - start_time

            if not missing_files:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="All required documentation files present",
                    details={"required_files": len(required_files)},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.WARNING,
                    message=f"Missing documentation files: {', '.join(missing_files)}",
                    details={"missing_files": missing_files},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )

        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.FAIL,
                message=f"Documentation completeness check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )


class PerformanceStandardsGate(QualityGate):
    """Gate 5: Performance Standards."""

    def __init__(self):
        super().__init__("Performance Standards", blocking=False)

    def validate(self, project_root: Path) -> GateResult:
        """Validate performance standards."""
        start_time = time.time()

        try:
            # Run reality checker for performance validation
            result = subprocess.run(
                [sys.executable, "docs/validation/reality_checker.py", "--check-performance"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=30,
            )

            execution_time = time.time() - start_time

            if result.returncode == 0:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.PASS,
                    message="Performance standards met",
                    details={"stdout": result.stdout[:300]},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )
            else:
                return GateResult(
                    gate_name=self.name,
                    status=GateStatus.WARNING,
                    message="Performance standards not fully met",
                    details={"stderr": result.stderr[:300]},
                    execution_time=execution_time,
                    timestamp=datetime.now(),
                    blocking=self.blocking,
                )

        except subprocess.TimeoutExpired:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.WARNING,
                message="Performance check timed out",
                details={"timeout": True},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )
        except Exception as e:
            return GateResult(
                gate_name=self.name,
                status=GateStatus.WARNING,
                message=f"Performance check failed: {str(e)}",
                details={"error": str(e)},
                execution_time=time.time() - start_time,
                timestamp=datetime.now(),
                blocking=self.blocking,
            )


class QualityGateEnforcer:
    """Enforces quality gates with fail-fast mechanisms."""

    def __init__(self, project_root: Path = None):
        """Initialize quality gate enforcer."""
        self.project_root = project_root or Path.cwd()

        # Define all quality gates
        self.gates = [
            DocumentationRealityGate(),
            CodeQualityGate(),
            SystemFunctionalityGate(),
            DocumentationCompletenessGate(),
            PerformanceStandardsGate(),
        ]

        self.results: list[GateResult] = []

    def enforce_gates(self, gate_types: list[str] = None) -> list[GateResult]:
        """Enforce quality gates with fail-fast behavior."""
        self.results.clear()

        # Filter gates if specific types requested
        gates_to_run = self.gates
        if gate_types:
            gates_to_run = [
                gate
                for gate in self.gates
                if any(gate_type.lower() in gate.name.lower() for gate_type in gate_types)
            ]

        # Run gates in order
        for gate in gates_to_run:
            print(f"Running {gate.name}...")
            result = gate.validate(self.project_root)
            self.results.append(result)

            # Print immediate feedback
            status_symbol = (
                "✅"
                if result.status == GateStatus.PASS
                else "⚠️" if result.status == GateStatus.WARNING else "❌"
            )
            print(f"{status_symbol} {gate.name}: {result.message}")

            # Fail fast on blocking failures
            if result.status == GateStatus.FAIL and result.blocking:
                print(f"BLOCKING FAILURE: {gate.name} failed - stopping execution")
                break

        return self.results

    def pre_commit_gates(self) -> list[GateResult]:
        """Run pre-commit quality gates."""
        return self.enforce_gates(["Code Quality", "Documentation Reality"])

    def ci_gates(self) -> list[GateResult]:
        """Run CI quality gates."""
        return self.enforce_gates()

    def deployment_gates(self) -> list[GateResult]:
        """Run deployment quality gates."""
        return self.enforce_gates()

    def generate_report(self) -> dict[str, Any]:
        """Generate quality gate report."""
        total_gates = len(self.results)
        passed_gates = sum(1 for r in self.results if r.status == GateStatus.PASS)
        failed_gates = sum(1 for r in self.results if r.status == GateStatus.FAIL)
        warning_gates = sum(1 for r in self.results if r.status == GateStatus.WARNING)

        # Calculate blocking failures
        blocking_failures = [r for r in self.results if r.status == GateStatus.FAIL and r.blocking]

        return {
            "summary": {
                "total_gates": total_gates,
                "passed": passed_gates,
                "failed": failed_gates,
                "warnings": warning_gates,
                "blocking_failures": len(blocking_failures),
                "success_rate": passed_gates / total_gates if total_gates > 0 else 1.0,
            },
            "blocking_failures": [
                {"gate": result.gate_name, "message": result.message, "details": result.details}
                for result in blocking_failures
            ],
            "all_results": [
                {
                    "gate": result.gate_name,
                    "status": result.status.value,
                    "message": result.message,
                    "execution_time": result.execution_time,
                    "timestamp": result.timestamp.isoformat(),
                    "blocking": result.blocking,
                    "details": result.details,
                }
                for result in self.results
            ],
        }

    def has_blocking_failures(self) -> bool:
        """Check if there are any blocking failures."""
        return any(r.status == GateStatus.FAIL and r.blocking for r in self.results)


def main():
    """Main entry point for quality gate enforcement."""
    import argparse

    parser = argparse.ArgumentParser(description="Enforce quality gates")
    parser.add_argument(
        "--gate",
        choices=[
            "documentation-reality",
            "code-quality",
            "system-functionality",
            "documentation-completeness",
            "performance-standards",
        ],
        help="Run specific quality gate",
    )
    parser.add_argument("--pre-commit", action="store_true", help="Run pre-commit gates")
    parser.add_argument("--ci", action="store_true", help="Run CI gates")
    parser.add_argument("--deployment", action="store_true", help="Run deployment gates")
    parser.add_argument("--enforce", action="store_true", help="Enforce all gates with fail-fast")
    parser.add_argument("--report", action="store_true", help="Generate quality gate report")
    parser.add_argument("--dashboard", action="store_true", help="Generate compliance dashboard")

    args = parser.parse_args()

    enforcer = QualityGateEnforcer()

    if args.pre_commit:
        results = enforcer.pre_commit_gates()
    elif args.ci:
        results = enforcer.ci_gates()
    elif args.deployment:
        results = enforcer.deployment_gates()
    elif args.gate:
        results = enforcer.enforce_gates([args.gate.replace("-", " ").title()])
    else:
        results = enforcer.enforce_gates()

    # Generate report if requested
    if args.report or args.dashboard:
        report = enforcer.generate_report()
        print(json.dumps(report, indent=2, default=str))

    # Print summary
    passed = sum(1 for r in results if r.status == GateStatus.PASS)
    failed = sum(1 for r in results if r.status == GateStatus.FAIL)
    warnings = sum(1 for r in results if r.status == GateStatus.WARNING)

    print(f"\nQuality Gates Summary: {passed} passed, {failed} failed, {warnings} warnings")

    # Exit with appropriate code
    if enforcer.has_blocking_failures():
        print("BLOCKING FAILURES DETECTED - Deployment blocked")
        sys.exit(1)
    elif failed > 0:
        print("NON-BLOCKING FAILURES DETECTED")
        sys.exit(1)
    else:
        print("ALL QUALITY GATES PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
