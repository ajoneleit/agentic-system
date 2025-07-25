"""
Base test verifier implementation.

This module provides a base class for test verifiers with common
functionality and utilities for running tests.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import (
    TestVerifierInterface,
    VerificationContext,
    VerificationResult
)
from src.verification.models import LanguageType, VerificationStage, VerificationStatus

logger = logging.getLogger(__name__)


class TestVerifier(TestVerifierInterface):
    """Base implementation for test verification."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the test verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Common configuration
        self.timeout = self.config.get("timeout", 300)  # 5 minutes default for tests
        self.enable_coverage = self.config.get("enable_coverage", True)
        self.coverage_threshold = self.config.get("coverage_threshold", 80.0)
        self.parallel_execution = self.config.get("parallel_execution", True)
        self.verbose_output = self.config.get("verbose_output", False)
        
        # Test discovery patterns
        self.test_patterns = self.config.get("test_patterns", [])
        self.exclude_patterns = self.config.get("exclude_patterns", [])
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages - to be overridden by subclasses."""
        return set()
    
    async def verify(self, context: VerificationContext) -> VerificationResult:
        """
        Perform test verification on the given context.
        
        Args:
            context: Verification context with file and configuration
            
        Returns:
            VerificationResult with detailed test results
        """
        started_at = datetime.utcnow()
        
        try:
            # Check if language is supported
            if context.language not in self.supported_languages:
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=self.verification_stage,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    error_message=f"Language {context.language.value} not supported by this test verifier"
                )
            
            # Discover test files
            test_files = await self.discover_tests(context)
            
            if not test_files:
                return VerificationResult(
                    success=True,
                    status=VerificationStatus.SKIPPED,
                    stage=self.verification_stage,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    output="No test files found",
                    metrics={"test_files_found": 0}
                )
            
            # Run the tests
            result = await self.run_tests(test_files, context)
            
            # Get coverage information if enabled
            if self.enable_coverage and result.success:
                try:
                    coverage_data = await self.get_coverage(context)
                    result.metrics.update(coverage_data)
                except Exception as e:
                    self.logger.warning(f"Failed to get coverage data: {str(e)}")
                    result.warnings.append(f"Coverage collection failed: {str(e)}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"Test verification failed: {str(e)}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Test verification error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def discover_tests(self, context: VerificationContext) -> List[Path]:
        """Discover test files - to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement discover_tests")
    
    async def run_tests(self, test_files: List[Path], context: VerificationContext) -> VerificationResult:
        """Run tests - to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement run_tests")
    
    async def get_coverage(self, context: VerificationContext) -> Dict[str, Any]:
        """Get test coverage - to be implemented by subclasses."""
        return {"coverage_enabled": False, "message": "Coverage not implemented for this language"}
    
    async def is_available(self) -> bool:
        """Check if this test verifier is available - to be implemented by subclasses."""
        return True
    
    def _discover_files_by_patterns(
        self, 
        root_path: Path, 
        patterns: List[str], 
        exclude_patterns: List[str] = None
    ) -> List[Path]:
        """
        Discover files matching the given patterns.
        
        Args:
            root_path: Root directory to search
            patterns: List of glob patterns to match
            exclude_patterns: List of glob patterns to exclude
            
        Returns:
            List of matching file paths
        """
        exclude_patterns = exclude_patterns or []
        found_files = []
        
        try:
            for pattern in patterns:
                for file_path in root_path.rglob(pattern):
                    if file_path.is_file():
                        # Check if file should be excluded
                        should_exclude = False
                        for exclude_pattern in exclude_patterns:
                            if file_path.match(exclude_pattern):
                                should_exclude = True
                                break
                        
                        if not should_exclude:
                            found_files.append(file_path)
            
            # Remove duplicates and sort
            found_files = sorted(list(set(found_files)))
            
        except Exception as e:
            self.logger.error(f"Error discovering files: {str(e)}")
        
        return found_files
    
    async def _run_command_with_timeout(
        self,
        command: List[str],
        working_dir: Optional[Path] = None,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Run a command with timeout and return structured results.
        
        Args:
            command: Command and arguments
            working_dir: Working directory
            timeout: Timeout in seconds
            env: Environment variables
            
        Returns:
            Dictionary with execution results
        """
        import subprocess
        
        timeout = timeout or self.timeout
        working_dir = working_dir or Path.cwd()
        start_time = datetime.utcnow()
        
        try:
            # Use asyncio.run_in_executor to avoid blocking
            loop = asyncio.get_running_loop()
            
            def run_subprocess():
                return subprocess.run(
                    command,
                    cwd=working_dir,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    env=env
                )
            
            process = await loop.run_in_executor(None, run_subprocess)
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "returncode": process.returncode,
                "stdout": process.stdout,
                "stderr": process.stderr,
                "execution_time": execution_time,
                "command": " ".join(command),
                "timeout": False
            }
            
        except subprocess.TimeoutExpired:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "execution_time": execution_time,
                "command": " ".join(command),
                "timeout": True
            }
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command execution failed: {str(e)}",
                "execution_time": execution_time,
                "command": " ".join(command),
                "error": str(e)
            }
    
    def _parse_test_summary(self, output: str) -> Dict[str, Any]:
        """
        Parse test output to extract summary information.
        Override in subclasses for language-specific parsing.
        
        Args:
            output: Test runner output
            
        Returns:
            Dictionary with parsed test summary
        """
        return {
            "total_tests": 0,
            "passed_tests": 0,
            "failed_tests": 0,
            "skipped_tests": 0,
            "parsing_method": "base_class_default"
        }
    
    def _extract_test_failures(self, output: str) -> List[Dict[str, Any]]:
        """
        Extract test failure information from output.
        Override in subclasses for language-specific parsing.
        
        Args:
            output: Test runner output
            
        Returns:
            List of test failure details
        """
        return []
    
    def _calculate_success_rate(self, summary: Dict[str, Any]) -> float:
        """Calculate test success rate from summary."""
        total = summary.get("total_tests", 0)
        passed = summary.get("passed_tests", 0)
        
        if total == 0:
            return 1.0  # No tests means success
        
        return passed / total