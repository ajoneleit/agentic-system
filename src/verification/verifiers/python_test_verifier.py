"""
Python test verifier implementation.

This module provides test verification capabilities for Python code using
pytest, unittest, and coverage.py.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import VerificationContext, VerificationResult
from src.verification.models import LanguageType, VerificationStage, VerificationStatus
from src.verification.verifiers.test_verifier import TestVerifier


class PythonTestVerifier(TestVerifier):
    """Python-specific test verifier using pytest."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the Python test verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        super().__init__(config)
        
        # Python-specific configuration
        self.test_framework = self.config.get("test_framework", "pytest")  # pytest, unittest
        self.pytest_config = self.config.get("pytest_config", None)  # pytest.ini, pyproject.toml
        self.coverage_config = self.config.get("coverage_config", None)  # .coveragerc
        
        # Test discovery patterns for Python
        self.test_patterns = self.config.get("test_patterns", [
            "test_*.py",
            "*_test.py",
            "tests/*.py",
            "test/**/*.py"
        ])
        
        # Pytest specific options
        self.pytest_options = self.config.get("pytest_options", ["-v"])
        self.collect_only = self.config.get("collect_only", False)
        self.markers = self.config.get("markers", [])  # pytest markers to run/skip
        
        # Coverage options
        self.coverage_source = self.config.get("coverage_source", [])
        self.coverage_omit = self.config.get("coverage_omit", [])
        self.coverage_report_format = self.config.get("coverage_report_format", "term")  # term, json, xml, html
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages."""
        return {LanguageType.PYTHON}
    
    async def discover_tests(self, context: VerificationContext) -> List[Path]:
        """
        Discover Python test files.
        
        Args:
            context: Verification context
            
        Returns:
            List of discovered test file paths
        """
        try:
            # Use pytest's test discovery if available
            if self.test_framework == "pytest" and await self._is_pytest_available():
                return await self._discover_tests_with_pytest(context)
            else:
                # Fallback to pattern-based discovery
                return self._discover_files_by_patterns(
                    context.project_root,
                    self.test_patterns,
                    self.exclude_patterns
                )
        except Exception as e:
            self.logger.error(f"Test discovery failed: {str(e)}")
            return []
    
    async def run_tests(self, test_files: List[Path], context: VerificationContext) -> VerificationResult:
        """
        Run Python tests using pytest or unittest.
        
        Args:
            test_files: List of test files to run
            context: Verification context
            
        Returns:
            VerificationResult with test execution results
        """
        started_at = datetime.utcnow()
        
        try:
            if self.test_framework == "pytest" and await self._is_pytest_available():
                return await self._run_pytest(test_files, context, started_at)
            else:
                return await self._run_unittest(test_files, context, started_at)
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Test execution error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def get_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """
        Get test coverage information using coverage.py.
        
        Args:
            context: Verification context
            
        Returns:
            Dictionary with coverage information
        """
        try:
            if not await self._is_coverage_available():
                return {
                    "coverage_enabled": False,
                    "message": "coverage.py not available"
                }
            
            # Run coverage report
            coverage_command = ["coverage", "report", "--format=json"]
            if self.coverage_config:
                coverage_command.extend(["--rcfile", str(self.coverage_config)])
            
            result = await self._run_command_with_timeout(
                coverage_command,
                working_dir=context.working_directory or context.project_root
            )
            
            if result["returncode"] == 0:
                try:
                    coverage_data = json.loads(result["stdout"])
                    return {
                        "coverage_enabled": True,
                        "total_coverage": coverage_data.get("totals", {}).get("percent_covered", 0.0),
                        "line_coverage": coverage_data.get("totals", {}).get("percent_covered_display", "0%"),
                        "files_covered": len(coverage_data.get("files", {})),
                        "missing_lines": coverage_data.get("totals", {}).get("missing_lines", 0),
                        "covered_lines": coverage_data.get("totals", {}).get("covered_lines", 0),
                        "total_lines": coverage_data.get("totals", {}).get("num_statements", 0),
                        "coverage_details": coverage_data
                    }
                except json.JSONDecodeError:
                    # Fallback to text parsing
                    return self._parse_coverage_text(result["stdout"])
            else:
                return {
                    "coverage_enabled": False,
                    "error": result["stderr"],
                    "message": "Coverage report generation failed"
                }
                
        except Exception as e:
            self.logger.error(f"Coverage collection failed: {str(e)}")
            return {
                "coverage_enabled": False,
                "error": str(e),
                "message": "Coverage collection error"
            }
    
    async def is_available(self) -> bool:
        """Check if Python test verifier is available."""
        # Check if we can import the test framework
        try:
            if self.test_framework == "pytest":
                return await self._is_pytest_available()
            else:
                # unittest is part of standard library
                import unittest
                return True
        except Exception:
            return False
    
    async def _discover_tests_with_pytest(self, context: VerificationContext) -> List[Path]:
        """Discover tests using pytest's collection."""
        try:
            command = ["pytest", "--collect-only", "-q"]
            
            # Add pytest config if specified
            if self.pytest_config:
                command.extend(["-c", str(self.pytest_config)])
            
            # Add markers if specified
            for marker in self.markers:
                command.extend(["-m", marker])
            
            # Add project root
            command.append(str(context.project_root))
            
            result = await self._run_command_with_timeout(
                command,
                working_dir=context.working_directory or context.project_root
            )
            
            if result["returncode"] == 0:
                # Parse pytest collection output
                test_files = []
                for line in result["stdout"].splitlines():
                    line = line.strip()
                    if line.endswith(".py"):
                        test_file = Path(line.split("::", 1)[0])
                        if test_file.exists():
                            test_files.append(test_file)
                
                return list(set(test_files))  # Remove duplicates
            else:
                self.logger.warning(f"Pytest collection failed: {result['stderr']}")
                return []
                
        except Exception as e:
            self.logger.error(f"Pytest test discovery failed: {str(e)}")
            return []
    
    async def _run_pytest(
        self, 
        test_files: List[Path], 
        context: VerificationContext, 
        started_at: datetime
    ) -> VerificationResult:
        """Run tests using pytest."""
        try:
            # Build pytest command
            pytest_command = ["pytest"]
            
            # Add configuration options
            pytest_command.extend(self.pytest_options)
            
            # Add coverage if enabled
            if self.enable_coverage:
                pytest_command.append("--cov")
                if self.coverage_source:
                    for source in self.coverage_source:
                        pytest_command.extend(["--cov", source])
                
                pytest_command.append("--cov-report=term-missing")
                pytest_command.append("--cov-report=json")
            
            # Add pytest config if specified
            if self.pytest_config:
                pytest_command.extend(["-c", str(self.pytest_config)])
            
            # Add markers if specified
            for marker in self.markers:
                pytest_command.extend(["-m", marker])
            
            # Add JSON report for structured output
            json_report_file = context.project_root / "pytest_report.json"
            pytest_command.extend(["--json-report", f"--json-report-file={json_report_file}"])
            
            # Add test files or directories
            if len(test_files) == 1 and test_files[0].is_dir():
                pytest_command.append(str(test_files[0]))
            else:
                pytest_command.extend([str(f) for f in test_files])
            
            # Run pytest
            result = await self._run_command_with_timeout(
                pytest_command,
                working_dir=context.working_directory or context.project_root,
                timeout=self.timeout
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            # Parse pytest results
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            # Try to parse JSON report if available
            test_summary = {}
            test_failures = []
            
            if json_report_file.exists():
                try:
                    with open(json_report_file, 'r') as f:
                        json_data = json.load(f)
                    
                    test_summary = self._parse_pytest_json(json_data)
                    test_failures = self._extract_pytest_failures(json_data)
                    
                    # Clean up report file
                    json_report_file.unlink()
                except Exception as e:
                    self.logger.warning(f"Failed to parse pytest JSON report: {str(e)}")
                    test_summary = self._parse_pytest_text(result["stdout"])
                    test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            else:
                # Parse text output
                test_summary = self._parse_pytest_text(result["stdout"])
                test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            
            # Calculate success rate
            success_rate = self._calculate_success_rate(test_summary)
            
            return VerificationResult(
                success=success,
                status=status,
                stage=self.verification_stage,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=completed_at,
                execution_time=execution_time,
                output=result["stdout"] if success else "",
                error_message=result["stderr"] if not success else "",
                error_details={
                    "test_failures": test_failures,
                    "command": result["command"],
                    "returncode": result["returncode"]
                },
                warnings=[f["message"] for f in test_failures if f.get("severity") == "warning"],
                metrics={
                    **test_summary,
                    "success_rate": success_rate,
                    "test_files_count": len(test_files),
                    "pytest_version": await self._get_pytest_version()
                },
                config={
                    "test_framework": self.test_framework,
                    "pytest_options": self.pytest_options,
                    "coverage_enabled": self.enable_coverage
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Pytest execution error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _run_unittest(
        self, 
        test_files: List[Path], 
        context: VerificationContext, 
        started_at: datetime
    ) -> VerificationResult:
        """Run tests using unittest."""
        try:
            # Build unittest command
            unittest_command = ["python", "-m", "unittest"]
            
            if self.verbose_output:
                unittest_command.append("-v")
            
            # Convert file paths to module names
            test_modules = []
            for test_file in test_files:
                try:
                    # Convert path to module name
                    relative_path = test_file.relative_to(context.project_root)
                    module_name = str(relative_path.with_suffix("")).replace("/", ".").replace("\\", ".")
                    test_modules.append(module_name)
                except ValueError:
                    # File is not within project root, use absolute path
                    unittest_command.append(str(test_file))
            
            unittest_command.extend(test_modules)
            
            # Run unittest
            result = await self._run_command_with_timeout(
                unittest_command,
                working_dir=context.working_directory or context.project_root,
                timeout=self.timeout
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            # Parse unittest results
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            test_summary = self._parse_unittest_output(result["stderr"] + result["stdout"])
            test_failures = self._extract_test_failures(result["stderr"] + result["stdout"])
            success_rate = self._calculate_success_rate(test_summary)
            
            return VerificationResult(
                success=success,
                status=status,
                stage=self.verification_stage,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=completed_at,
                execution_time=execution_time,
                output=result["stdout"] if success else "",
                error_message=result["stderr"] if not success else "",
                error_details={
                    "test_failures": test_failures,
                    "command": result["command"],
                    "returncode": result["returncode"]
                },
                metrics={
                    **test_summary,
                    "success_rate": success_rate,
                    "test_files_count": len(test_files)
                },
                config={
                    "test_framework": self.test_framework,
                    "verbose": self.verbose_output
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=LanguageType.PYTHON,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Unittest execution error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _is_pytest_available(self) -> bool:
        """Check if pytest is available."""
        try:
            result = await self._run_command_with_timeout(["pytest", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _is_coverage_available(self) -> bool:
        """Check if coverage.py is available."""
        try:
            result = await self._run_command_with_timeout(["coverage", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _get_pytest_version(self) -> str:
        """Get pytest version."""
        try:
            result = await self._run_command_with_timeout(["pytest", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    def _parse_pytest_json(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse pytest JSON report."""
        summary = json_data.get("summary", {})
        return {
            "total_tests": summary.get("total", 0),
            "passed_tests": summary.get("passed", 0),
            "failed_tests": summary.get("failed", 0),
            "skipped_tests": summary.get("skipped", 0),
            "error_tests": summary.get("error", 0),
            "duration": json_data.get("duration", 0.0),
            "parsing_method": "pytest_json"
        }
    
    def _parse_pytest_text(self, output: str) -> Dict[str, Any]:
        """Parse pytest text output."""
        # Look for pytest summary line like "===== 5 passed, 1 failed in 2.34s ====="
        summary_pattern = r"=+ (.+) in ([\d.]+)s =+"
        match = re.search(summary_pattern, output)
        
        if match:
            summary_text = match.group(1)
            duration = float(match.group(2))
            
            # Parse individual counts
            passed = self._extract_count(summary_text, "passed")
            failed = self._extract_count(summary_text, "failed")
            skipped = self._extract_count(summary_text, "skipped")
            errors = self._extract_count(summary_text, "error")
            
            return {
                "total_tests": passed + failed + skipped + errors,
                "passed_tests": passed,
                "failed_tests": failed,
                "skipped_tests": skipped,
                "error_tests": errors,
                "duration": duration,
                "parsing_method": "pytest_text"
            }
        
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "parsing_method": "pytest_text_fallback"
        }
    
    def _parse_unittest_output(self, output: str) -> Dict[str, Any]:
        """Parse unittest output."""
        # Look for unittest summary like "Ran 5 tests in 2.345s"
        ran_pattern = r"Ran (\d+) tests? in ([\d.]+)s"
        match = re.search(ran_pattern, output)
        
        total_tests = 0
        duration = 0.0
        
        if match:
            total_tests = int(match.group(1))
            duration = float(match.group(2))
        
        # Count failures and errors
        failure_count = len(re.findall(r"FAIL:", output))
        error_count = len(re.findall(r"ERROR:", output))
        
        # Check for OK or FAILED
        if "OK" in output:
            passed_tests = total_tests
            failed_tests = 0
        else:
            failed_tests = failure_count + error_count
            passed_tests = total_tests - failed_tests
        
        return {
            "total_tests": total_tests,
            "passed_tests": max(0, passed_tests),
            "failed_tests": failed_tests,
            "skipped_tests": 0,  # unittest doesn't easily show skipped in summary
            "duration": duration,
            "parsing_method": "unittest_text"
        }
    
    def _extract_count(self, text: str, keyword: str) -> int:
        """Extract count for a keyword from pytest summary."""
        pattern = rf"(\d+) {keyword}"
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0
    
    def _extract_pytest_failures(self, json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract failure details from pytest JSON."""
        failures = []
        
        for test in json_data.get("tests", []):
            if test.get("outcome") in ["failed", "error"]:
                failures.append({
                    "test_name": test.get("nodeid", ""),
                    "message": test.get("call", {}).get("longrepr", ""),
                    "file": test.get("lineno", 0),
                    "line": test.get("lineno", 0),
                    "severity": "error" if test.get("outcome") == "error" else "failure"
                })
        
        return failures
    
    def _parse_coverage_text(self, output: str) -> Dict[str, Any]:
        """Parse text coverage report."""
        # Simple text parsing for coverage
        total_pattern = r"TOTAL\s+\d+\s+\d+\s+(\d+)%"
        match = re.search(total_pattern, output)
        
        if match:
            coverage_percent = float(match.group(1))
            return {
                "coverage_enabled": True,
                "total_coverage": coverage_percent,
                "line_coverage": f"{coverage_percent}%",
                "parsing_method": "text_coverage"
            }
        
        return {
            "coverage_enabled": False,
            "message": "Could not parse coverage from text output"
        }