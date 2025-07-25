"""
JavaScript/TypeScript test verifier implementation.

This module provides test verification capabilities for JavaScript and TypeScript
code using Jest, Mocha, and other testing frameworks.
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import VerificationContext, VerificationResult
from src.verification.models import LanguageType, VerificationStage, VerificationStatus
from src.verification.verifiers.test_verifier import TestVerifier


class JavaScriptTestVerifier(TestVerifier):
    """JavaScript/TypeScript-specific test verifier using Jest and Mocha."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the JavaScript test verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        super().__init__(config)
        
        # JavaScript-specific configuration
        self.test_framework = self.config.get("test_framework", "jest")  # jest, mocha, jasmine
        self.jest_config = self.config.get("jest_config", None)  # jest.config.js
        self.mocha_config = self.config.get("mocha_config", None)  # .mocharc.json
        
        # Test discovery patterns for JavaScript/TypeScript
        self.test_patterns = self.config.get("test_patterns", [
            "**/*.test.js",
            "**/*.test.ts",
            "**/*.spec.js", 
            "**/*.spec.ts",
            "test/**/*.js",
            "test/**/*.ts",
            "tests/**/*.js",
            "tests/**/*.ts",
            "__tests__/**/*.js",
            "__tests__/**/*.ts"
        ])
        
        # Jest specific options
        self.jest_options = self.config.get("jest_options", ["--verbose"])
        self.collect_coverage = self.config.get("collect_coverage", True)
        self.coverage_threshold = self.config.get("coverage_threshold", 80.0)
        
        # Mocha specific options
        self.mocha_options = self.config.get("mocha_options", ["--reporter", "json"])
        self.mocha_timeout = self.config.get("mocha_timeout", 5000)
        
        # Node.js configuration
        self.node_version = self.config.get("node_version", "latest")
        self.enable_typescript = self.config.get("enable_typescript", True)
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages."""
        languages = {LanguageType.JAVASCRIPT}
        if self.enable_typescript:
            languages.add(LanguageType.TYPESCRIPT)
        return languages
    
    async def discover_tests(self, context: VerificationContext) -> List[Path]:
        """
        Discover JavaScript/TypeScript test files.
        
        Args:
            context: Verification context
            
        Returns:
            List of discovered test file paths
        """
        try:
            # Use framework-specific test discovery if available
            if self.test_framework == "jest" and await self._is_jest_available():
                return await self._discover_tests_with_jest(context)
            elif self.test_framework == "mocha" and await self._is_mocha_available():
                return await self._discover_tests_with_mocha(context)
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
        Run JavaScript/TypeScript tests using Jest or Mocha.
        
        Args:
            test_files: List of test files to run
            context: Verification context
            
        Returns:
            VerificationResult with test execution results
        """
        started_at = datetime.utcnow()
        
        try:
            if self.test_framework == "jest" and await self._is_jest_available():
                return await self._run_jest(test_files, context, started_at)
            elif self.test_framework == "mocha" and await self._is_mocha_available():
                return await self._run_mocha(test_files, context, started_at)
            else:
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=self.verification_stage,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    error_message=f"Test framework '{self.test_framework}' not available",
                    error_details={"missing_framework": self.test_framework}
                )
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Test execution error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def get_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """
        Get test coverage information using Jest coverage or nyc.
        
        Args:
            context: Verification context
            
        Returns:
            Dictionary with coverage information
        """
        try:
            if self.test_framework == "jest" and await self._is_jest_available():
                return await self._get_jest_coverage(context)
            elif await self._is_nyc_available():
                return await self._get_nyc_coverage(context)
            else:
                return {
                    "coverage_enabled": False,
                    "message": "No coverage tool available (Jest or nyc)"
                }
                
        except Exception as e:
            self.logger.error(f"Coverage collection failed: {str(e)}")
            return {
                "coverage_enabled": False,
                "error": str(e),
                "message": "Coverage collection error"
            }
    
    async def is_available(self) -> bool:
        """Check if JavaScript test verifier is available."""
        # Check if Node.js is available
        if not await self._is_node_available():
            return False
        
        # Check if at least one test framework is available
        if self.test_framework == "jest":
            return await self._is_jest_available()
        elif self.test_framework == "mocha":
            return await self._is_mocha_available()
        else:
            return False
    
    async def _discover_tests_with_jest(self, context: VerificationContext) -> List[Path]:
        """Discover tests using Jest's test discovery."""
        try:
            command = ["jest", "--listTests"]
            
            # Add Jest config if specified
            if self.jest_config:
                command.extend(["--config", str(self.jest_config)])
            
            # Add project root
            command = ["npx"] + command
            
            result = await self._run_command_with_timeout(
                command,
                working_dir=context.working_directory or context.project_root
            )
            
            if result["returncode"] == 0:
                # Parse Jest test list output
                test_files = []
                for line in result["stdout"].splitlines():
                    line = line.strip()
                    if line and Path(line).exists():
                        test_files.append(Path(line))
                
                return test_files
            else:
                self.logger.warning(f"Jest test discovery failed: {result['stderr']}")
                return []
                
        except Exception as e:
            self.logger.error(f"Jest test discovery failed: {str(e)}")
            return []
    
    async def _discover_tests_with_mocha(self, context: VerificationContext) -> List[Path]:
        """Discover tests using pattern matching for Mocha."""
        try:
            # Mocha doesn't have built-in test discovery like Jest
            # Use pattern-based discovery with Mocha-specific patterns
            mocha_patterns = [
                "test/**/*.js",
                "test/**/*.ts", 
                "spec/**/*.js",
                "spec/**/*.ts",
                "**/*.test.js",
                "**/*.test.ts",
                "**/*.spec.js",
                "**/*.spec.ts"
            ]
            
            return self._discover_files_by_patterns(
                context.project_root,
                mocha_patterns,
                self.exclude_patterns
            )
                
        except Exception as e:
            self.logger.error(f"Mocha test discovery failed: {str(e)}")
            return []
    
    async def _run_jest(
        self, 
        test_files: List[Path], 
        context: VerificationContext, 
        started_at: datetime
    ) -> VerificationResult:
        """Run tests using Jest."""
        try:
            # Build Jest command
            jest_command = ["npx", "jest"]
            
            # Add configuration options
            jest_command.extend(self.jest_options)
            
            # Add coverage if enabled
            if self.enable_coverage and self.collect_coverage:
                jest_command.append("--coverage")
                jest_command.extend(["--coverageReporters", "json", "text"])
            
            # Add Jest config if specified
            if self.jest_config:
                jest_command.extend(["--config", str(self.jest_config)])
            
            # Add JSON reporter for structured output
            jest_command.extend(["--json", "--outputFile=jest-results.json"])
            
            # Add test file patterns or specific files
            if len(test_files) == 1 and test_files[0].is_dir():
                # If single directory, let Jest handle discovery
                pass
            else:
                # Add specific test files as patterns
                for test_file in test_files:
                    jest_command.append(str(test_file.relative_to(context.project_root)))
            
            # Run Jest
            result = await self._run_command_with_timeout(
                jest_command,
                working_dir=context.working_directory or context.project_root,
                timeout=self.timeout
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            # Parse Jest results
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            # Try to parse JSON report if available
            test_summary = {}
            test_failures = []
            
            jest_results_file = context.project_root / "jest-results.json"
            if jest_results_file.exists():
                try:
                    with open(jest_results_file, 'r') as f:
                        json_data = json.load(f)
                    
                    test_summary = self._parse_jest_json(json_data)
                    test_failures = self._extract_jest_failures(json_data)
                    
                    # Clean up report file
                    jest_results_file.unlink()
                except Exception as e:
                    self.logger.warning(f"Failed to parse Jest JSON report: {str(e)}")
                    test_summary = self._parse_jest_text(result["stdout"])
                    test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            else:
                # Parse text output
                test_summary = self._parse_jest_text(result["stdout"])
                test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            
            # Calculate success rate
            success_rate = self._calculate_success_rate(test_summary)
            
            return VerificationResult(
                success=success,
                status=status,
                stage=self.verification_stage,
                language=context.language,
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
                    "jest_version": await self._get_jest_version()
                },
                config={
                    "test_framework": self.test_framework,
                    "jest_options": self.jest_options,
                    "coverage_enabled": self.enable_coverage and self.collect_coverage
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Jest execution error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _run_mocha(
        self, 
        test_files: List[Path], 
        context: VerificationContext, 
        started_at: datetime
    ) -> VerificationResult:
        """Run tests using Mocha."""
        try:
            # Build Mocha command
            mocha_command = ["npx", "mocha"]
            
            # Add configuration options
            mocha_command.extend(self.mocha_options)
            
            # Add timeout
            mocha_command.extend(["--timeout", str(self.mocha_timeout)])
            
            # Add Mocha config if specified
            if self.mocha_config:
                mocha_command.extend(["--config", str(self.mocha_config)])
            
            # Add TypeScript support if enabled
            if self.enable_typescript:
                mocha_command.extend(["--require", "ts-node/register"])
            
            # Add test files
            mocha_command.extend([str(f) for f in test_files])
            
            # Run Mocha
            result = await self._run_command_with_timeout(
                mocha_command,
                working_dir=context.working_directory or context.project_root,
                timeout=self.timeout
            )
            
            completed_at = datetime.utcnow()
            execution_time = result["execution_time"]
            
            # Parse Mocha results
            success = result["returncode"] == 0
            status = VerificationStatus.SUCCESS if success else VerificationStatus.FAILED
            
            # Try to parse JSON output if JSON reporter was used
            test_summary = {}
            test_failures = []
            
            if "--reporter json" in " ".join(self.mocha_options):
                try:
                    json_data = json.loads(result["stdout"])
                    test_summary = self._parse_mocha_json(json_data)
                    test_failures = self._extract_mocha_failures(json_data)
                except json.JSONDecodeError:
                    test_summary = self._parse_mocha_text(result["stdout"])
                    test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            else:
                # Parse text output
                test_summary = self._parse_mocha_text(result["stdout"])
                test_failures = self._extract_test_failures(result["stdout"] + result["stderr"])
            
            # Calculate success rate
            success_rate = self._calculate_success_rate(test_summary)
            
            return VerificationResult(
                success=success,
                status=status,
                stage=self.verification_stage,
                language=context.language,
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
                    "mocha_version": await self._get_mocha_version()
                },
                config={
                    "test_framework": self.test_framework,
                    "mocha_options": self.mocha_options,
                    "timeout": self.mocha_timeout
                }
            )
            
        except Exception as e:
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Mocha execution error: {str(e)}",
                error_details={"exception": str(e)}
            )
    
    async def _get_jest_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """Get coverage information from Jest."""
        try:
            coverage_file = context.project_root / "coverage" / "coverage-summary.json"
            if coverage_file.exists():
                with open(coverage_file, 'r') as f:
                    coverage_data = json.load(f)
                
                total_coverage = coverage_data.get("total", {})
                return {
                    "coverage_enabled": True,
                    "total_coverage": total_coverage.get("lines", {}).get("pct", 0.0),
                    "line_coverage": f"{total_coverage.get('lines', {}).get('pct', 0.0)}%",
                    "branch_coverage": total_coverage.get("branches", {}).get("pct", 0.0),
                    "function_coverage": total_coverage.get("functions", {}).get("pct", 0.0),
                    "statement_coverage": total_coverage.get("statements", {}).get("pct", 0.0),
                    "coverage_details": coverage_data
                }
            else:
                return {
                    "coverage_enabled": False,
                    "message": "Jest coverage file not found"
                }
                
        except Exception as e:
            return {
                "coverage_enabled": False,
                "error": str(e),
                "message": "Jest coverage parsing failed"
            }
    
    async def _get_nyc_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """Get coverage information using nyc (Istanbul)."""
        try:
            # Run nyc report to get coverage data
            nyc_command = ["npx", "nyc", "report", "--reporter=json"]
            
            result = await self._run_command_with_timeout(
                nyc_command,
                working_dir=context.working_directory or context.project_root
            )
            
            if result["returncode"] == 0:
                try:
                    coverage_data = json.loads(result["stdout"])
                    # Calculate totals from nyc JSON format
                    total_lines = sum(file_data["lines"]["total"] for file_data in coverage_data.values())
                    covered_lines = sum(file_data["lines"]["covered"] for file_data in coverage_data.values())
                    
                    coverage_percent = (covered_lines / total_lines * 100) if total_lines > 0 else 0.0
                    
                    return {
                        "coverage_enabled": True,
                        "total_coverage": coverage_percent,
                        "line_coverage": f"{coverage_percent:.1f}%",
                        "covered_lines": covered_lines,
                        "total_lines": total_lines,
                        "files_covered": len(coverage_data),
                        "coverage_details": coverage_data
                    }
                except json.JSONDecodeError:
                    return self._parse_nyc_text(result["stdout"])
            else:
                return {
                    "coverage_enabled": False,
                    "error": result["stderr"],
                    "message": "nyc coverage report failed"
                }
                
        except Exception as e:
            return {
                "coverage_enabled": False,
                "error": str(e),
                "message": "nyc coverage collection error"
            }
    
    async def _is_node_available(self) -> bool:
        """Check if Node.js is available."""
        try:
            result = await self._run_command_with_timeout(["node", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _is_jest_available(self) -> bool:
        """Check if Jest is available."""
        try:
            result = await self._run_command_with_timeout(["npx", "jest", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _is_mocha_available(self) -> bool:
        """Check if Mocha is available."""
        try:
            result = await self._run_command_with_timeout(["npx", "mocha", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _is_nyc_available(self) -> bool:
        """Check if nyc (Istanbul) is available."""
        try:
            result = await self._run_command_with_timeout(["npx", "nyc", "--version"], timeout=10)
            return result["returncode"] == 0
        except Exception:
            return False
    
    async def _get_jest_version(self) -> str:
        """Get Jest version."""
        try:
            result = await self._run_command_with_timeout(["npx", "jest", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    async def _get_mocha_version(self) -> str:
        """Get Mocha version."""
        try:
            result = await self._run_command_with_timeout(["npx", "mocha", "--version"], timeout=10)
            if result["returncode"] == 0:
                return result["stdout"].strip()
            return "unknown"
        except Exception:
            return "unknown"
    
    def _parse_jest_json(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Jest JSON report."""
        return {
            "total_tests": json_data.get("numTotalTests", 0),
            "passed_tests": json_data.get("numPassedTests", 0),
            "failed_tests": json_data.get("numFailedTests", 0),
            "skipped_tests": json_data.get("numPendingTests", 0),
            "duration": json_data.get("testResults", [{}])[0].get("perfStats", {}).get("runtime", 0) / 1000.0,
            "parsing_method": "jest_json"
        }
    
    def _parse_jest_text(self, output: str) -> Dict[str, Any]:
        """Parse Jest text output."""
        # Look for Jest summary line like "Tests: 1 failed, 4 passed, 5 total"
        summary_pattern = r"Tests:\s+(.+)"
        match = re.search(summary_pattern, output)
        
        if match:
            summary_text = match.group(1)
            
            # Parse individual counts
            passed = self._extract_count(summary_text, "passed")
            failed = self._extract_count(summary_text, "failed")
            skipped = self._extract_count(summary_text, "skipped")
            total = self._extract_count(summary_text, "total")
            
            # Look for time
            time_pattern = r"Time:\s+([0-9.]+)\s*s"
            time_match = re.search(time_pattern, output)
            duration = float(time_match.group(1)) if time_match else 0.0
            
            return {
                "total_tests": total or (passed + failed + skipped),
                "passed_tests": passed,
                "failed_tests": failed,
                "skipped_tests": skipped,
                "duration": duration,
                "parsing_method": "jest_text"
            }
        
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "parsing_method": "jest_text_fallback"
        }
    
    def _parse_mocha_json(self, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Mocha JSON report."""
        stats = json_data.get("stats", {})
        return {
            "total_tests": stats.get("tests", 0),
            "passed_tests": stats.get("passes", 0),
            "failed_tests": stats.get("failures", 0),
            "skipped_tests": stats.get("pending", 0),
            "duration": stats.get("duration", 0) / 1000.0,
            "parsing_method": "mocha_json"
        }
    
    def _parse_mocha_text(self, output: str) -> Dict[str, Any]:
        """Parse Mocha text output.""" 
        # Look for Mocha summary like "5 passing (123ms)" and "1 failing"
        passing_pattern = r"(\d+) passing"
        failing_pattern = r"(\d+) failing"
        pending_pattern = r"(\d+) pending"
        
        passed = 0
        failed = 0
        skipped = 0
        
        passing_match = re.search(passing_pattern, output)
        if passing_match:
            passed = int(passing_match.group(1))
        
        failing_match = re.search(failing_pattern, output)
        if failing_match:
            failed = int(failing_match.group(1))
        
        pending_match = re.search(pending_pattern, output)
        if pending_match:
            skipped = int(pending_match.group(1))
        
        # Look for duration
        duration_pattern = r"(\d+)ms"
        duration_match = re.search(duration_pattern, output)
        duration = float(duration_match.group(1)) / 1000.0 if duration_match else 0.0
        
        return {
            "total_tests": passed + failed + skipped,
            "passed_tests": passed,
            "failed_tests": failed,
            "skipped_tests": skipped,
            "duration": duration,
            "parsing_method": "mocha_text"
        }
    
    def _extract_count(self, text: str, keyword: str) -> int:
        """Extract count for a keyword from test summary."""
        pattern = rf"(\d+) {keyword}"
        match = re.search(pattern, text)
        return int(match.group(1)) if match else 0
    
    def _extract_jest_failures(self, json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract failure details from Jest JSON."""
        failures = []
        
        for test_result in json_data.get("testResults", []):
            for assertion in test_result.get("assertionResults", []):
                if assertion.get("status") == "failed":
                    failures.append({
                        "test_name": assertion.get("fullName", ""),
                        "message": assertion.get("failureMessages", [""])[0],
                        "file": test_result.get("name", ""),
                        "line": 0,  # Jest doesn't provide line numbers in JSON
                        "severity": "failure"
                    })
        
        return failures
    
    def _extract_mocha_failures(self, json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract failure details from Mocha JSON."""
        failures = []
        
        for failure in json_data.get("failures", []):
            failures.append({
                "test_name": failure.get("fullTitle", ""),
                "message": failure.get("err", {}).get("message", ""),
                "file": failure.get("file", ""),
                "line": 0,  # Mocha JSON doesn't always provide line numbers
                "severity": "failure"
            })
        
        return failures
    
    def _parse_nyc_text(self, output: str) -> Dict[str, Any]:
        """Parse text nyc coverage report."""
        # Simple text parsing for nyc coverage
        total_pattern = r"All files\s+\|\s+([0-9.]+)\s+\|"
        match = re.search(total_pattern, output)
        
        if match:
            coverage_percent = float(match.group(1))
            return {
                "coverage_enabled": True,
                "total_coverage": coverage_percent,
                "line_coverage": f"{coverage_percent}%",
                "parsing_method": "nyc_text_coverage"
            }
        
        return {
            "coverage_enabled": False,
            "message": "Could not parse coverage from nyc text output"
        }