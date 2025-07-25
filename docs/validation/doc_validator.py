#!/usr/bin/env python3
"""Documentation Validator - Enforces Reality > Aspirations principle.

This module validates that all documentation claims are backed by actual
code, tests, or verifiable metrics.
"""

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""

    passed: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    file_path: Optional[str] = None
    line_number: Optional[int] = None


class ValidationType(Enum):
    """Types of validation checks."""

    CODE_REFERENCE = "code_reference"
    EXAMPLE_EXECUTION = "example_execution"
    PERFORMANCE_CLAIM = "performance_claim"
    PROCESS_CLAIM = "process_claim"
    COMPLETENESS = "completeness"
    STRUCTURE = "structure"


class DocumentationValidator:
    """Validates documentation against reality."""

    def __init__(self, project_root: Path = None):
        """Initialize validator with project root."""
        self.project_root = project_root or Path.cwd()
        self.docs_root = self.project_root / "docs"
        self.src_root = self.project_root / "src"
        self.examples_root = self.project_root / "examples"
        self.scripts_root = self.project_root / "scripts"

        self.validation_results: list[ValidationResult] = []

    def validate_all(self) -> list[ValidationResult]:
        """Run all validation checks."""
        self.validation_results.clear()

        # Find all documentation files
        doc_files = list(self.docs_root.rglob("*.md"))

        for doc_file in doc_files:
            self._validate_file(doc_file)

        return self.validation_results

    def _validate_file(self, doc_file: Path) -> None:
        """Validate a single documentation file."""
        try:
            content = doc_file.read_text(encoding="utf-8")

            # Validate code references
            self._validate_code_references(doc_file, content)

            # Validate examples
            self._validate_examples(doc_file, content)

            # Validate performance claims
            self._validate_performance_claims(doc_file, content)

            # Validate process claims
            self._validate_process_claims(doc_file, content)

        except Exception as e:
            self.validation_results.append(
                ValidationResult(
                    passed=False,
                    message=f"Failed to validate {doc_file}: {str(e)}",
                    file_path=str(doc_file),
                )
            )

    def _validate_code_references(self, doc_file: Path, content: str) -> None:
        """Validate that all code references point to actual code."""
        # Pattern to match code references like `src/agents/meta_agent.py`
        code_ref_pattern = r"`([^`]+\.py)`"
        refs = re.findall(code_ref_pattern, content)

        for ref in refs:
            # Resolve relative to project root
            code_path = self.project_root / ref

            if not code_path.exists():
                self.validation_results.append(
                    ValidationResult(
                        passed=False,
                        message=f"Code reference '{ref}' points to non-existent file",
                        file_path=str(doc_file),
                        details={"referenced_file": ref},
                    )
                )
            else:
                # Validate that referenced functions/classes exist
                self._validate_code_entities(doc_file, content, code_path, ref)

    def _validate_code_entities(
        self, doc_file: Path, content: str, code_path: Path, ref: str
    ) -> None:
        """Validate that referenced functions/classes exist in code."""
        # Pattern to match function/class references like `MetaAgent.process_request`
        entity_pattern = rf'{ref.split("/")[-1].replace(".py", "")}\.(\w+)'
        entities = re.findall(entity_pattern, content)

        if entities:
            try:
                # Parse the Python file to check for entities
                code_content = code_path.read_text(encoding="utf-8")
                tree = ast.parse(code_content)

                # Extract all function and class names
                existing_entities = set()
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                        existing_entities.add(node.name)

                # Check each referenced entity
                for entity in entities:
                    if entity not in existing_entities:
                        self.validation_results.append(
                            ValidationResult(
                                passed=False,
                                message=f"Referenced entity '{entity}' not found in {ref}",
                                file_path=str(doc_file),
                                details={"entity": entity, "code_file": ref},
                            )
                        )

            except Exception as e:
                self.validation_results.append(
                    ValidationResult(
                        passed=False,
                        message=f"Failed to parse {ref}: {str(e)}",
                        file_path=str(doc_file),
                    )
                )

    def _validate_examples(self, doc_file: Path, content: str) -> None:
        """Validate that all code examples are executable."""
        # Pattern to match code blocks with bash or python
        code_block_pattern = r"```(?:bash|python)\n(.*?)\n```"
        examples = re.findall(code_block_pattern, content, re.DOTALL)

        for i, example in enumerate(examples):
            if example.strip().startswith("#"):
                continue  # Skip commented examples

            # Validate bash commands
            if any(cmd in example for cmd in ["python", "pip", "git"]):
                self._validate_bash_example(doc_file, example, i)

            # Validate Python code
            if "import" in example or "from" in example:
                self._validate_python_example(doc_file, example, i)

    def _validate_bash_example(self, doc_file: Path, example: str, index: int) -> None:
        """Validate that bash examples are syntactically correct."""
        lines = example.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Check for common patterns that should exist
            if line.startswith("python "):
                script_path = line.split()[1]
                if not script_path.startswith("-"):  # Not a flag
                    full_path = self.project_root / script_path
                    if not full_path.exists():
                        self.validation_results.append(
                            ValidationResult(
                                passed=False,
                                message=f"Example references non-existent script: {script_path}",
                                file_path=str(doc_file),
                                details={"example_index": index, "script": script_path},
                            )
                        )

    def _validate_python_example(self, doc_file: Path, example: str, index: int) -> None:
        """Validate that Python examples are syntactically correct."""
        try:
            # Try to parse the Python code
            ast.parse(example)

            # Check imports
            tree = ast.parse(example)
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    module_path = node.module
                    if module_path and module_path.startswith("src."):
                        # Convert module path to file path
                        file_path = self.project_root / module_path.replace(".", "/") + ".py"
                        if not file_path.exists():
                            self.validation_results.append(
                                ValidationResult(
                                    passed=False,
                                    message=f"Example imports non-existent module: {module_path}",
                                    file_path=str(doc_file),
                                    details={"example_index": index, "module": module_path},
                                )
                            )

        except SyntaxError as e:
            self.validation_results.append(
                ValidationResult(
                    passed=False,
                    message=f"Python example has syntax error: {str(e)}",
                    file_path=str(doc_file),
                    details={"example_index": index},
                )
            )

    def _validate_performance_claims(self, doc_file: Path, content: str) -> None:
        """Validate that performance claims have supporting data."""
        # Pattern to match performance claims like "88.3% improvement" or "< 5 seconds"
        perf_patterns = [
            r"(\d+\.?\d*%)\s+(?:improvement|faster|reduction)",
            r"<\s*(\d+)\s+seconds?",
            r"(\d+\.?\d*x)\s+(?:faster|throughput|speedup)",
        ]

        for pattern in perf_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                # Check if there's a corresponding benchmark file or data
                self._check_performance_data_exists(doc_file, match)

    def _check_performance_data_exists(self, doc_file: Path, claim: str) -> None:
        """Check if performance data exists to support claim."""
        # Look for benchmark files
        benchmark_dirs = [
            self.project_root / "benchmarks",
            self.project_root / "tests" / "performance",
            self.project_root / "docs" / "metrics",
        ]

        has_supporting_data = False
        for bench_dir in benchmark_dirs:
            if bench_dir.exists():
                has_supporting_data = True
                break

        if not has_supporting_data:
            self.validation_results.append(
                ValidationResult(
                    passed=False,
                    message=f"Performance claim '{claim}' lacks supporting benchmark data",
                    file_path=str(doc_file),
                    details={"claim": claim},
                )
            )

    def _validate_process_claims(self, doc_file: Path, content: str) -> None:
        """Validate that process descriptions have executable implementations."""
        # Look for process descriptions that should have corresponding scripts
        process_patterns = [r"run\s+`([^`]+)`", r"execute\s+`([^`]+)`", r"command:\s*`([^`]+)`"]

        for pattern in process_patterns:
            commands = re.findall(pattern, content, re.IGNORECASE)
            for command in commands:
                self._validate_command_exists(doc_file, command)

    def _validate_command_exists(self, doc_file: Path, command: str) -> None:
        """Validate that a command or script exists."""
        if command.startswith("python "):
            script_name = command.split()[1]
            script_path = self.project_root / script_name

            if not script_path.exists():
                self.validation_results.append(
                    ValidationResult(
                        passed=False,
                        message=f"Process references non-existent script: {script_name}",
                        file_path=str(doc_file),
                        details={"command": command},
                    )
                )

    def validate_structure(self) -> ValidationResult:
        """Validate that documentation structure follows standards."""
        required_files = [
            "index.md",
            "development/setup.md",
            "development/coding-standards.md",
            "processes/quality-gates.md",
            "validation/doc_validator.py",
        ]

        missing_files = []
        for req_file in required_files:
            file_path = self.docs_root / req_file
            if not file_path.exists():
                missing_files.append(req_file)

        if missing_files:
            return ValidationResult(
                passed=False,
                message=f"Missing required documentation files: {', '.join(missing_files)}",
                details={"missing_files": missing_files},
            )

        return ValidationResult(passed=True, message="Documentation structure is valid")

    def generate_report(self) -> dict[str, Any]:
        """Generate comprehensive validation report."""
        total_checks = len(self.validation_results)
        passed_checks = sum(1 for r in self.validation_results if r.passed)
        failed_checks = total_checks - passed_checks

        # Group failures by type
        failures_by_file = {}
        for result in self.validation_results:
            if not result.passed and result.file_path:
                file_key = result.file_path
                if file_key not in failures_by_file:
                    failures_by_file[file_key] = []
                failures_by_file[file_key].append(result.message)

        return {
            "summary": {
                "total_checks": total_checks,
                "passed": passed_checks,
                "failed": failed_checks,
                "success_rate": passed_checks / total_checks if total_checks > 0 else 1.0,
            },
            "failures_by_file": failures_by_file,
            "detailed_results": [
                {
                    "passed": r.passed,
                    "message": r.message,
                    "file": r.file_path,
                    "line": r.line_number,
                    "details": r.details,
                }
                for r in self.validation_results
            ],
        }


def main():
    """Main entry point for documentation validation."""
    import argparse

    parser = argparse.ArgumentParser(description="Validate documentation against reality")
    parser.add_argument(
        "--check-structure", action="store_true", help="Check documentation structure"
    )
    parser.add_argument("--check-code-refs", action="store_true", help="Check code references")
    parser.add_argument("--test-examples", action="store_true", help="Test example code")
    parser.add_argument(
        "--check-completeness", action="store_true", help="Check documentation completeness"
    )
    parser.add_argument("--generate-report", action="store_true", help="Generate validation report")
    parser.add_argument("--fail-fast", action="store_true", help="Exit on first failure")

    args = parser.parse_args()

    validator = DocumentationValidator()

    if args.check_structure:
        result = validator.validate_structure()
        if not result.passed:
            print(f"FAIL: {result.message}")
            if args.fail_fast:
                sys.exit(1)

    if any([args.check_code_refs, args.test_examples, args.check_completeness]) or not any(
        vars(args).values()
    ):
        results = validator.validate_all()

        # Print results
        failed_results = [r for r in results if not r.passed]
        if failed_results:
            print(f"VALIDATION FAILED: {len(failed_results)} issues found")
            for result in failed_results:
                print(f"  - {result.message}")
                if result.file_path:
                    print(f"    File: {result.file_path}")

            if args.fail_fast:
                sys.exit(1)
        else:
            print("VALIDATION PASSED: All documentation claims verified")

    if args.generate_report:
        report = validator.generate_report()
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
