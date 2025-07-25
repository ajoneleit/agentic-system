"""
Base compiler verifier implementation.

This module provides a base class for compiler verifiers with common
functionality and utilities.
"""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.verification.interfaces import (
    CompilerVerifierInterface,
    VerificationContext,
    VerificationResult
)
from src.verification.models import LanguageType, VerificationStage, VerificationStatus

logger = logging.getLogger(__name__)


class CompilerVerifier(CompilerVerifierInterface):
    """Base implementation for compiler verification."""
    
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the compiler verifier.
        
        Args:
            config: Configuration dictionary for the verifier
        """
        self.config = config or {}
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Common configuration
        self.timeout = self.config.get("timeout", 30)
        self.enable_warnings = self.config.get("enable_warnings", True)
        self.strict_mode = self.config.get("strict_mode", False)
    
    @property
    def supported_languages(self) -> Set[LanguageType]:
        """Return supported languages - to be overridden by subclasses."""
        return set()
    
    async def verify(self, context: VerificationContext) -> VerificationResult:
        """
        Perform verification on the given context.
        
        Args:
            context: Verification context with file and configuration
            
        Returns:
            VerificationResult with detailed results
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
                    error_message=f"Language {context.language.value} not supported by this verifier"
                )
            
            # Check if file exists
            if not context.file_path.exists():
                return VerificationResult(
                    success=False,
                    status=VerificationStatus.ERROR,
                    stage=self.verification_stage,
                    language=context.language,
                    started_at=started_at,
                    completed_at=datetime.utcnow(),
                    error_message=f"File not found: {context.file_path}"
                )
            
            # Perform syntax check
            syntax_result = await self.check_syntax(context.file_path, context)
            
            # If syntax check failed, return early
            if not syntax_result.success:
                return syntax_result
            
            # Optionally perform type checking
            if self.config.get("enable_type_checking", True):
                type_result = await self.check_types(context.file_path, context)
                if not type_result.success:
                    # Combine results - syntax passed but types failed
                    syntax_result.success = False
                    syntax_result.status = VerificationStatus.FAILED
                    syntax_result.error_message = type_result.error_message
                    syntax_result.error_details.update(type_result.error_details)
                    syntax_result.warnings.extend(type_result.warnings)
            
            return syntax_result
            
        except Exception as e:
            self.logger.error(f"Compiler verification failed: {str(e)}")
            return VerificationResult(
                success=False,
                status=VerificationStatus.ERROR,
                stage=self.verification_stage,
                language=context.language,
                started_at=started_at,
                completed_at=datetime.utcnow(),
                error_message=f"Verification error: {str(e)}",
                error_details={"exception": str(e), "type": type(e).__name__}
            )
    
    async def check_syntax(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """Check syntax of the given file - to be implemented by subclasses."""
        raise NotImplementedError("Subclasses must implement check_syntax")
    
    async def check_types(self, file_path: Path, context: VerificationContext) -> VerificationResult:
        """Check types in the given file - to be implemented by subclasses."""
        # Default implementation - no type checking
        return VerificationResult(
            success=True,
            status=VerificationStatus.SUCCESS,
            stage=VerificationStage.TYPE_CHECK,
            language=context.language,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            output="Type checking not implemented for this language"
        )
    
    async def is_available(self) -> bool:
        """Check if this verifier is available - to be implemented by subclasses."""
        return True
    
    async def _run_command(
        self,
        command: List[str],
        working_dir: Optional[Path] = None,
        timeout: Optional[int] = None,
        env: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Run a command asynchronously and return the result.
        
        Args:
            command: Command and arguments to run
            working_dir: Working directory for the command
            timeout: Timeout in seconds
            env: Environment variables
            
        Returns:
            Dictionary with returncode, stdout, stderr, and execution_time
        """
        timeout = timeout or self.timeout
        working_dir = working_dir or Path.cwd()
        
        start_time = datetime.utcnow()
        
        try:
            # Use asyncio.run_in_executor to avoid blocking the event loop
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
                "command": " ".join(command)
            }
            
        except subprocess.TimeoutExpired as e:
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
    
    def _parse_file_info(self, file_path: Path) -> Dict[str, Any]:
        """Parse basic file information."""
        try:
            stat = file_path.stat()
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                line_count = len(content.splitlines())
            
            return {
                "file_size": stat.st_size,
                "line_count": line_count,
                "modified_time": datetime.fromtimestamp(stat.st_mtime),
                "encoding": "utf-8"
            }
        except Exception as e:
            self.logger.warning(f"Failed to parse file info for {file_path}: {str(e)}")
            return {"error": str(e)}