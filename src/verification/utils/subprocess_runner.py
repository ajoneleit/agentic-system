"""Safe subprocess execution utilities."""

import asyncio
import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from src.utils.app_logging import get_logger


logger = get_logger(__name__)


@dataclass
class RunResult:
    """Result from running a subprocess."""
    
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    exception: Optional[str] = None
    
    @property
    def success(self) -> bool:
        """Check if the command succeeded."""
        return self.returncode == 0 and not self.timed_out and not self.exception


class SubprocessRunner:
    """Safe subprocess execution with timeout and resource limits."""
    
    def __init__(
        self,
        timeout_seconds: int = 30,
        capture_output: bool = True,
        env: Optional[Dict[str, str]] = None,
    ):
        """Initialize subprocess runner.
        
        Args:
            timeout_seconds: Maximum execution time
            capture_output: Whether to capture stdout/stderr
            env: Environment variables to use
        """
        self.timeout_seconds = timeout_seconds
        self.capture_output = capture_output
        self.env = env or os.environ.copy()
        self.is_windows = platform.system() == "Windows"
    
    async def run(
        self,
        command: Union[str, List[str]],
        cwd: Optional[Path] = None,
        input_data: Optional[str] = None,
        shell: bool = False,
    ) -> RunResult:
        """Run a command asynchronously.
        
        Args:
            command: Command to run (string or list)
            cwd: Working directory
            input_data: Input to send to stdin
            shell: Whether to use shell execution
            
        Returns:
            RunResult with output and status
        """
        # Convert command to list if string
        if isinstance(command, str) and not shell:
            command = command.split()
        
        logger.info(f"Running command: {command}")
        
        try:
            # Create subprocess
            if shell:
                proc = await asyncio.create_subprocess_shell(
                    command,
                    stdout=subprocess.PIPE if self.capture_output else None,
                    stderr=subprocess.PIPE if self.capture_output else None,
                    stdin=subprocess.PIPE if input_data else None,
                    cwd=cwd,
                    env=self.env,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=subprocess.PIPE if self.capture_output else None,
                    stderr=subprocess.PIPE if self.capture_output else None,
                    stdin=subprocess.PIPE if input_data else None,
                    cwd=cwd,
                    env=self.env,
                )
            
            # Run with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(input=input_data.encode() if input_data else None),
                    timeout=self.timeout_seconds
                )
                
                return RunResult(
                    returncode=proc.returncode,
                    stdout=stdout.decode('utf-8', errors='replace') if stdout else "",
                    stderr=stderr.decode('utf-8', errors='replace') if stderr else "",
                    timed_out=False,
                )
                
            except asyncio.TimeoutError:
                # Kill the process
                try:
                    proc.kill()
                    await proc.wait()
                except ProcessLookupError:
                    pass
                
                return RunResult(
                    returncode=-1,
                    stdout="",
                    stderr=f"Process timed out after {self.timeout_seconds} seconds",
                    timed_out=True,
                )
                
        except Exception as e:
            logger.error(f"Subprocess execution failed: {e}")
            return RunResult(
                returncode=-1,
                stdout="",
                stderr="",
                exception=str(e),
            )
    
    async def run_python(
        self,
        script_path: Path,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
    ) -> RunResult:
        """Run a Python script.
        
        Args:
            script_path: Path to Python script
            args: Additional arguments
            cwd: Working directory
            
        Returns:
            RunResult
        """
        command = [sys.executable, str(script_path)]
        if args:
            command.extend(args)
        
        return await self.run(command, cwd=cwd)
    
    async def run_python_module(
        self,
        module: str,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
    ) -> RunResult:
        """Run a Python module.
        
        Args:
            module: Module name (e.g., "pytest")
            args: Additional arguments
            cwd: Working directory
            
        Returns:
            RunResult
        """
        command = [sys.executable, "-m", module]
        if args:
            command.extend(args)
        
        return await self.run(command, cwd=cwd)
    
    async def run_node(
        self,
        script_path: Optional[Path] = None,
        code: Optional[str] = None,
        args: Optional[List[str]] = None,
        cwd: Optional[Path] = None,
    ) -> RunResult:
        """Run Node.js code or script.
        
        Args:
            script_path: Path to JavaScript file
            code: JavaScript code to execute
            args: Additional arguments
            cwd: Working directory
            
        Returns:
            RunResult
        """
        if script_path:
            command = ["node", str(script_path)]
        elif code:
            command = ["node", "-e", code]
        else:
            raise ValueError("Either script_path or code must be provided")
        
        if args:
            command.extend(args)
        
        return await self.run(command, cwd=cwd)
    
    async def check_command_available(self, command: str) -> bool:
        """Check if a command is available in the system.
        
        Args:
            command: Command to check
            
        Returns:
            True if command is available
        """
        check_command = "where" if self.is_windows else "which"
        result = await self.run([check_command, command])
        return result.success


# Convenience functions

async def run_command(
    command: Union[str, List[str]],
    timeout: int = 30,
    cwd: Optional[Path] = None,
    capture_output: bool = True,
) -> RunResult:
    """Run a command with default settings.
    
    Args:
        command: Command to run
        timeout: Timeout in seconds
        cwd: Working directory
        capture_output: Whether to capture output
        
    Returns:
        RunResult
    """
    runner = SubprocessRunner(
        timeout_seconds=timeout,
        capture_output=capture_output,
    )
    return await runner.run(command, cwd=cwd)


async def run_python_code(
    code: str,
    timeout: int = 30,
    cwd: Optional[Path] = None,
) -> RunResult:
    """Run Python code directly.
    
    Args:
        code: Python code to execute
        timeout: Timeout in seconds
        cwd: Working directory
        
    Returns:
        RunResult
    """
    runner = SubprocessRunner(timeout_seconds=timeout)
    return await runner.run(
        [sys.executable, "-c", code],
        cwd=cwd
    )


async def check_python_syntax(code: str) -> bool:
    """Check if Python code has valid syntax.
    
    Args:
        code: Python code to check
        
    Returns:
        True if syntax is valid
    """
    result = await run_python_code(
        f"import ast; ast.parse({repr(code)})",
        timeout=5
    )
    return result.success