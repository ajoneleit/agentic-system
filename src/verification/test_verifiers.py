"""Test execution verifiers for different testing frameworks."""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.interfaces import Artifact, ArtifactType
from src.utils.app_logging import get_logger

from .verifier_base import (
    BaseVerifier,
    VerificationConfig,
    VerificationError,
    VerificationResult,
    VerificationType,
)


logger = get_logger(__name__)


@dataclass
class TestResult:
    """Individual test result."""
    
    name: str
    status: str  # passed, failed, skipped, error
    duration: float = 0.0
    error_message: Optional[str] = None
    error_traceback: Optional[str] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


@dataclass
class TestSuiteResult:
    """Results from running a test suite."""
    
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    skipped_tests: int = 0
    error_tests: int = 0
    
    execution_time: float = 0.0
    coverage_percent: Optional[float] = None
    
    test_results: List[TestResult] = field(default_factory=list)
    coverage_details: Dict[str, Any] = field(default_factory=dict)


class PythonTestVerifier(BaseVerifier):
    """Python test verifier using pytest."""
    
    def __init__(self, config: Optional[VerificationConfig] = None):
        super().__init__(config)
        self._supported_languages = {"python"}
        self._supported_artifact_types = {ArtifactType.TEST_CODE}
    
    @property
    def name(self) -> str:
        return "PythonTestVerifier"
    
    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.TEST
    
    async def verify(self, artifact: Artifact, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Run Python tests using pytest.
        
        Args:
            artifact: The test code artifact
            context: Optional context including related source code
            
        Returns:
            Verification result with test execution details
        """
        result = self._create_result(artifact)
        
        try:
            # Check if pytest is available
            if not await self._check_pytest_available():
                result.add_error("pytest is not available")
                result.add_suggestion("Install pytest: pip install pytest pytest-cov")
                result.complete()
                return result
            
            # Prepare test environment
            test_dir = await self._prepare_test_environment(artifact, context)
            
            # Run tests
            test_suite_result = await self._run_pytest(test_dir)
            
            # Process results
            self._process_test_results(test_suite_result, result)
            
            # Check coverage if enabled
            if self.config.enable_tests and test_suite_result.coverage_percent is not None:
                if test_suite_result.coverage_percent < self.config.test_coverage_threshold * 100:
                    result.add_warning(
                        f"Code coverage ({test_suite_result.coverage_percent:.1f}%) "
                        f"is below threshold ({self.config.test_coverage_threshold * 100:.0f}%)"
                    )
                    result.add_suggestion("Add more tests to improve code coverage")
            
            # Generate suggestions for failures
            if not result.success:
                self._generate_test_suggestions(test_suite_result, result)
            
        except Exception as e:
            logger.error(f"Unexpected error during Python test verification: {e}")
            result.add_error(f"Test verification failed: {str(e)}")
        
        result.complete()
        return result
    
    async def _check_pytest_available(self) -> bool:
        """Check if pytest is available."""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pytest", "--version",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await proc.communicate()
            return proc.returncode == 0
        except Exception:
            return False
    
    async def _prepare_test_environment(self, artifact: Artifact, context: Optional[Dict[str, Any]]) -> Path:
        """Prepare a temporary directory with test and source files."""
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Write test file
            test_content = artifact.content
            if not test_content and artifact.path and artifact.path.exists():
                test_content = artifact.path.read_text(encoding='utf-8')
            
            # Ensure the test file name starts with "test_" for pytest discovery
            test_filename = artifact.name or "test_code.py"
            if not test_filename.startswith("test_"):
                test_filename = f"test_{test_filename}"
            
            test_file = temp_dir / test_filename
            test_file.write_text(test_content, encoding='utf-8')
            
            # Write related source files if provided in context
            if context and "source_artifacts" in context:
                for source_artifact in context["source_artifacts"]:
                    if isinstance(source_artifact, Artifact):
                        source_content = source_artifact.content
                        if not source_content and source_artifact.path and source_artifact.path.exists():
                            source_content = source_artifact.path.read_text(encoding='utf-8')
                        
                        source_file = temp_dir / (source_artifact.name or "source_code.py")
                        source_file.write_text(source_content, encoding='utf-8')
            
            # Create __init__.py to make it a package
            (temp_dir / "__init__.py").touch()
            
            return temp_dir
            
        except Exception as e:
            # Clean up on error
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    
    async def _run_pytest(self, test_dir: Path) -> TestSuiteResult:
        """Run pytest and collect results."""
        result = TestSuiteResult()
        
        # Prepare pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_dir),
            "--tb=short",  # Short traceback format
            "--verbose",
        ]
        
        # Check available plugins and add optional flags
        check_cmd = [sys.executable, "-m", "pytest", "--help"]
        try:
            check_proc = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            stdout, _ = await check_proc.communicate()
            
            # Add timeout if available
            if b"--timeout" in stdout:
                cmd.append(f"--timeout={self.config.test_timeout_seconds}")
            
            # Add json-report if available
            if b"--json-report" in stdout:
                cmd.extend(["--json-report", "--json-report-file=report.json"])
        except Exception:
            pass  # Continue with basic options
        
        # Add coverage if available
        try:
            import pytest_cov
            cmd.extend(["--cov=.", "--cov-report=json"])
        except ImportError:
            logger.info("pytest-cov not available, skipping coverage")
        
        # Run pytest
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(test_dir)
            )
            
            stdout, stderr = await proc.communicate()
            
            # Parse JSON report if available
            report_file = test_dir / "report.json"
            if report_file.exists():
                with open(report_file) as f:
                    report_data = json.load(f)
                
                # Extract test results
                result.total_tests = report_data["summary"]["total"]
                result.passed_tests = report_data["summary"]["passed"]
                result.failed_tests = report_data["summary"]["failed"]
                result.skipped_tests = report_data["summary"]["skipped"]
                result.execution_time = report_data["duration"]
                
                # Extract individual test results
                for test_data in report_data.get("tests", []):
                    test_result = TestResult(
                        name=test_data["nodeid"],
                        status="passed" if test_data["outcome"] == "passed" else "failed",
                        duration=test_data.get("duration", 0.0),
                    )
                    
                    if test_data["outcome"] == "failed":
                        test_result.error_message = test_data.get("call", {}).get("longrepr")
                    
                    result.test_results.append(test_result)
            
            # Parse coverage if available
            coverage_file = test_dir / "coverage.json"
            if coverage_file.exists():
                with open(coverage_file) as f:
                    coverage_data = json.load(f)
                    result.coverage_percent = coverage_data["totals"]["percent_covered"]
                    result.coverage_details = coverage_data
            
            # Fallback to parsing stdout if no JSON report
            if not report_file.exists():
                self._parse_pytest_output(stdout.decode(), stderr.decode(), result)
            
        except asyncio.TimeoutError:
            result.error_tests = 1
            test_result = TestResult(
                name="test_execution",
                status="error",
                error_message=f"Test execution timed out after {self.config.test_timeout_seconds} seconds"
            )
            result.test_results.append(test_result)
        except Exception as e:
            result.error_tests = 1
            test_result = TestResult(
                name="test_execution",
                status="error",
                error_message=f"Failed to run tests: {str(e)}"
            )
            result.test_results.append(test_result)
        finally:
            # Clean up
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)
        
        return result
    
    def _parse_pytest_output(self, stdout: str, stderr: str, result: TestSuiteResult) -> None:
        """Parse pytest output as fallback when JSON report is not available."""
        lines = stdout.splitlines()
        
        for line in lines:
            # Look for test result lines
            if " PASSED" in line:
                result.passed_tests += 1
                result.total_tests += 1
            elif " FAILED" in line:
                result.failed_tests += 1
                result.total_tests += 1
            elif " SKIPPED" in line:
                result.skipped_tests += 1
                result.total_tests += 1
            elif " ERROR" in line:
                result.error_tests += 1
                result.total_tests += 1
            
            # Look for summary line
            if "passed" in line and "failed" in line:
                # Parse summary like "1 passed, 2 failed in 0.5s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        try:
                            result.passed_tests = int(parts[i-1])
                        except ValueError:
                            pass
                    elif part == "failed" and i > 0:
                        try:
                            result.failed_tests = int(parts[i-1])
                        except ValueError:
                            pass
    
    def _process_test_results(self, test_suite_result: TestSuiteResult, result: VerificationResult) -> None:
        """Process test suite results into verification result."""
        # Update metrics
        result.metrics.tests_total = test_suite_result.total_tests
        result.metrics.tests_passed = test_suite_result.passed_tests
        result.metrics.tests_failed = test_suite_result.failed_tests
        result.metrics.tests_skipped = test_suite_result.skipped_tests
        result.metrics.execution_time = test_suite_result.execution_time
        
        if test_suite_result.coverage_percent is not None:
            result.metrics.coverage_percent = test_suite_result.coverage_percent
        
        # Determine success
        if test_suite_result.failed_tests > 0 or test_suite_result.error_tests > 0:
            result.success = False
            result.add_error(
                f"{test_suite_result.failed_tests + test_suite_result.error_tests} tests failed"
            )
            
            # Add details of failed tests
            for test_result in test_suite_result.test_results:
                if test_result.status in ["failed", "error"]:
                    result.add_error(f"Test '{test_result.name}' failed: {test_result.error_message}")
        else:
            result.add_info(
                f"All {test_suite_result.passed_tests} tests passed"
            )
        
        # Store detailed results
        result.details["test_results"] = [
            {
                "name": tr.name,
                "status": tr.status,
                "duration": tr.duration,
                "error": tr.error_message,
            }
            for tr in test_suite_result.test_results
        ]
        
        if test_suite_result.coverage_details:
            result.details["coverage"] = test_suite_result.coverage_details
    
    def _generate_test_suggestions(self, test_suite_result: TestSuiteResult, result: VerificationResult) -> None:
        """Generate suggestions for test failures."""
        if test_suite_result.failed_tests > 0:
            result.add_suggestion("Review failed test cases and fix the implementation")
            result.add_suggestion("Check test assertions and expected values")
            
            # Analyze common failure patterns
            error_patterns = []
            for test_result in test_suite_result.test_results:
                if test_result.error_message:
                    if "AssertionError" in test_result.error_message:
                        error_patterns.append("assertion")
                    elif "ImportError" in test_result.error_message:
                        error_patterns.append("import")
                    elif "AttributeError" in test_result.error_message:
                        error_patterns.append("attribute")
            
            if "assertion" in error_patterns:
                result.add_suggestion("Check that function outputs match expected values")
            if "import" in error_patterns:
                result.add_suggestion("Ensure all required modules are imported correctly")
            if "attribute" in error_patterns:
                result.add_suggestion("Verify that all class attributes and methods exist")


class JavaScriptTestVerifier(BaseVerifier):
    """JavaScript test verifier using Jest or Mocha."""
    
    def __init__(self, config: Optional[VerificationConfig] = None):
        super().__init__(config)
        self._supported_languages = {"javascript", "typescript"}
        self._supported_artifact_types = {ArtifactType.TEST_CODE}
    
    @property
    def name(self) -> str:
        return "JavaScriptTestVerifier"
    
    @property
    def verification_type(self) -> VerificationType:
        return VerificationType.TEST
    
    async def verify(self, artifact: Artifact, context: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """Run JavaScript tests using available test runner.
        
        Args:
            artifact: The test code artifact
            context: Optional context including related source code
            
        Returns:
            Verification result with test execution details
        """
        result = self._create_result(artifact)
        
        try:
            # Check which test runner is available
            test_runner = await self._detect_test_runner()
            
            if not test_runner:
                result.add_error("No JavaScript test runner available (Jest or Mocha)")
                result.add_suggestion("Install a test runner: npm install --save-dev jest")
                result.complete()
                return result
            
            # Prepare test environment
            test_dir = await self._prepare_test_environment(artifact, context)
            
            # Run tests based on available runner
            if test_runner == "jest":
                test_suite_result = await self._run_jest(test_dir)
            else:  # mocha
                test_suite_result = await self._run_mocha(test_dir)
            
            # Process results
            self._process_test_results(test_suite_result, result)
            
        except Exception as e:
            logger.error(f"Unexpected error during JavaScript test verification: {e}")
            result.add_error(f"Test verification failed: {str(e)}")
        
        result.complete()
        return result
    
    async def _detect_test_runner(self) -> Optional[str]:
        """Detect which JavaScript test runner is available."""
        # Check for Jest
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "jest", "--version",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return "jest"
        except Exception:
            pass
        
        # Check for Mocha
        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "mocha", "--version",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            await proc.communicate()
            if proc.returncode == 0:
                return "mocha"
        except Exception:
            pass
        
        return None
    
    async def _prepare_test_environment(self, artifact: Artifact, context: Optional[Dict[str, Any]]) -> Path:
        """Prepare a temporary directory with test and source files."""
        temp_dir = Path(tempfile.mkdtemp())
        
        try:
            # Write test file
            test_content = artifact.content
            if not test_content and artifact.path and artifact.path.exists():
                test_content = artifact.path.read_text(encoding='utf-8')
            
            test_file = temp_dir / (artifact.name or "test.spec.js")
            test_file.write_text(test_content, encoding='utf-8')
            
            # Write related source files if provided
            if context and "source_artifacts" in context:
                for source_artifact in context["source_artifacts"]:
                    if isinstance(source_artifact, Artifact):
                        source_content = source_artifact.content
                        if not source_content and source_artifact.path and source_artifact.path.exists():
                            source_content = source_artifact.path.read_text(encoding='utf-8')
                        
                        source_file = temp_dir / (source_artifact.name or "source.js")
                        source_file.write_text(source_content, encoding='utf-8')
            
            # Create minimal package.json
            package_json = {
                "name": "test-project",
                "version": "1.0.0",
                "type": "module",
                "scripts": {
                    "test": "jest"
                }
            }
            (temp_dir / "package.json").write_text(json.dumps(package_json, indent=2))
            
            return temp_dir
            
        except Exception as e:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    
    async def _run_jest(self, test_dir: Path) -> TestSuiteResult:
        """Run Jest tests."""
        result = TestSuiteResult()
        
        # Create Jest config
        jest_config = {
            "testEnvironment": "node",
            "coverageDirectory": "coverage",
            "collectCoverageFrom": ["**/*.js", "!**/*.spec.js", "!**/*.test.js"],
        }
        
        config_file = test_dir / "jest.config.json"
        config_file.write_text(json.dumps(jest_config, indent=2))
        
        cmd = [
            "npx", "jest",
            "--config", str(config_file),
            "--json",
            "--coverage",
            f"--testTimeout={self.config.test_timeout_seconds * 1000}",  # Jest uses milliseconds
        ]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(test_dir)
            )
            
            stdout, stderr = await proc.communicate()
            
            # Parse Jest JSON output
            try:
                jest_result = json.loads(stdout.decode())
                
                result.total_tests = jest_result["numTotalTests"]
                result.passed_tests = jest_result["numPassedTests"]
                result.failed_tests = jest_result["numFailedTests"]
                result.skipped_tests = jest_result["numPendingTests"]
                
                # Extract test results
                for test_suite in jest_result.get("testResults", []):
                    for test in test_suite.get("assertionResults", []):
                        test_result = TestResult(
                            name=test["title"],
                            status="passed" if test["status"] == "passed" else "failed",
                            duration=test.get("duration", 0) / 1000.0,  # Convert to seconds
                        )
                        
                        if test["status"] == "failed":
                            test_result.error_message = "\n".join(test.get("failureMessages", []))
                        
                        result.test_results.append(test_result)
                
            except json.JSONDecodeError:
                # Fallback to parsing text output
                self._parse_jest_text_output(stdout.decode(), stderr.decode(), result)
                
        except Exception as e:
            result.error_tests = 1
            result.test_results.append(TestResult(
                name="test_execution",
                status="error",
                error_message=f"Failed to run Jest: {str(e)}"
            ))
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)
        
        return result
    
    async def _run_mocha(self, test_dir: Path) -> TestSuiteResult:
        """Run Mocha tests."""
        result = TestSuiteResult()
        
        cmd = [
            "npx", "mocha",
            "**/*.spec.js", "**/*.test.js",
            "--reporter", "json",
            f"--timeout", str(self.config.test_timeout_seconds * 1000),
        ]
        
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(test_dir)
            )
            
            stdout, stderr = await proc.communicate()
            
            # Parse Mocha JSON output
            try:
                mocha_result = json.loads(stdout.decode())
                
                result.total_tests = mocha_result["stats"]["tests"]
                result.passed_tests = mocha_result["stats"]["passes"]
                result.failed_tests = mocha_result["stats"]["failures"]
                result.skipped_tests = mocha_result["stats"]["pending"]
                result.execution_time = mocha_result["stats"]["duration"] / 1000.0
                
                # Extract test results from tests array
                for test in mocha_result.get("tests", []):
                    test_result = TestResult(
                        name=test["title"],
                        status="passed" if test.get("pass") else "failed",
                        duration=test.get("duration", 0) / 1000.0,
                    )
                    
                    if test.get("err"):
                        test_result.error_message = test["err"].get("message")
                        test_result.error_traceback = test["err"].get("stack")
                    
                    result.test_results.append(test_result)
                
            except json.JSONDecodeError:
                self._parse_mocha_text_output(stdout.decode(), stderr.decode(), result)
                
        except Exception as e:
            result.error_tests = 1
            result.test_results.append(TestResult(
                name="test_execution",
                status="error",
                error_message=f"Failed to run Mocha: {str(e)}"
            ))
        finally:
            import shutil
            shutil.rmtree(test_dir, ignore_errors=True)
        
        return result
    
    def _parse_jest_text_output(self, stdout: str, stderr: str, result: TestSuiteResult) -> None:
        """Parse Jest text output as fallback."""
        lines = stdout.splitlines()
        
        for line in lines:
            if "PASS" in line:
                result.passed_tests += 1
                result.total_tests += 1
            elif "FAIL" in line:
                result.failed_tests += 1
                result.total_tests += 1
    
    def _parse_mocha_text_output(self, stdout: str, stderr: str, result: TestSuiteResult) -> None:
        """Parse Mocha text output as fallback."""
        lines = stdout.splitlines()
        
        for line in lines:
            if "passing" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passing" and i > 0:
                        try:
                            result.passed_tests = int(parts[i-1])
                        except ValueError:
                            pass
            elif "failing" in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "failing" and i > 0:
                        try:
                            result.failed_tests = int(parts[i-1])
                        except ValueError:
                            pass
        
        result.total_tests = result.passed_tests + result.failed_tests
    
    def _process_test_results(self, test_suite_result: TestSuiteResult, result: VerificationResult) -> None:
        """Process test suite results into verification result."""
        # Same as Python version
        result.metrics.tests_total = test_suite_result.total_tests
        result.metrics.tests_passed = test_suite_result.passed_tests
        result.metrics.tests_failed = test_suite_result.failed_tests
        result.metrics.tests_skipped = test_suite_result.skipped_tests
        result.metrics.execution_time = test_suite_result.execution_time
        
        if test_suite_result.coverage_percent is not None:
            result.metrics.coverage_percent = test_suite_result.coverage_percent
        
        if test_suite_result.failed_tests > 0 or test_suite_result.error_tests > 0:
            result.success = False
            result.add_error(
                f"{test_suite_result.failed_tests + test_suite_result.error_tests} tests failed"
            )
            
            for test_result in test_suite_result.test_results:
                if test_result.status in ["failed", "error"]:
                    result.add_error(f"Test '{test_result.name}' failed: {test_result.error_message}")
        else:
            result.add_info(f"All {test_suite_result.passed_tests} tests passed")
        
        result.details["test_results"] = [
            {
                "name": tr.name,
                "status": tr.status,
                "duration": tr.duration,
                "error": tr.error_message,
            }
            for tr in test_suite_result.test_results
        ]