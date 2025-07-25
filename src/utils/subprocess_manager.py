"""Safe subprocess execution manager for Claude CLI with resource monitoring.

This module provides secure subprocess execution with memory limits, timeouts,
and output streaming to prevent resource exhaustion.
"""

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil
from structlog import get_logger

from src.core.exceptions import SubprocessError, SubprocessMemoryError

logger = get_logger(__name__)


@dataclass
class CLIExecutionResult:
    """Result of CLI execution with metrics."""

    stdout: str
    stderr: str
    exit_code: int
    execution_time: float
    memory_peak_mb: float
    cpu_time: float
    truncated: bool = False
    timeout_reached: bool = False
    memory_limit_reached: bool = False

    @property
    def success(self) -> bool:
        """Check if execution was successful."""
        return self.exit_code == 0 and not self.timeout_reached and not self.memory_limit_reached


class ProcessMonitor:
    """Monitors a running process for resource usage."""

    def __init__(self, pid: int, memory_limit_mb: float, output_limit_bytes: int):
        """Initialize process monitor.

        Args:
            pid: Process ID to monitor
            memory_limit_mb: Memory limit in megabytes
            output_limit_bytes: Maximum output size in bytes

        """
        self.pid = pid
        self.memory_limit_mb = memory_limit_mb
        self.output_limit_bytes = output_limit_bytes
        self.memory_peak_mb = 0.0
        self.cpu_time = 0.0
        self._start_time = time.time()

        try:
            self.process = psutil.Process(pid)
        except psutil.NoSuchProcess:
            self.process = None

    async def check_limits(self, current_output_size: int) -> tuple[bool, str]:
        """Check if process exceeds limits.

        Args:
            current_output_size: Current size of captured output

        Returns:
            Tuple of (limit_exceeded, reason)

        """
        if not self.process or not self.process.is_running():
            return False, ""

        try:
            # Check memory usage
            memory_info = self.process.memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)
            self.memory_peak_mb = max(self.memory_peak_mb, memory_mb)

            if memory_mb > self.memory_limit_mb:
                return True, f"Memory limit exceeded: {memory_mb:.1f}MB > {self.memory_limit_mb}MB"

            # Check output size
            if current_output_size > self.output_limit_bytes:
                return (
                    True,
                    f"Output limit exceeded: {current_output_size} > {self.output_limit_bytes} bytes",
                )

            # Update CPU time
            cpu_times = self.process.cpu_times()
            self.cpu_time = cpu_times.user + cpu_times.system

            return False, ""

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False, ""

    def get_metrics(self) -> dict[str, float]:
        """Get process metrics."""
        return {
            "memory_peak_mb": self.memory_peak_mb,
            "cpu_time": self.cpu_time,
            "wall_time": time.time() - self._start_time,
        }


class SafeSubprocessManager:
    """Manages safe subprocess execution with resource constraints."""

    def __init__(self):
        """Initialize subprocess manager."""
        self._active_processes: dict[int, asyncio.subprocess.Process] = {}
        logger.info("SafeSubprocessManager initialized")

    async def execute_claude_cli(
        self,
        prompt_content: str,
        mcp_config: Path,
        allowed_tools: list[str],
        timeout: int = 600,
        max_memory_mb: int = 2048,
        max_output_mb: int = 10,
        working_directory: Optional[Path] = None,
        env_vars: Optional[dict[str, str]] = None,
        stream_output: bool = True,
    ) -> CLIExecutionResult:
        """Execute Claude CLI with safety constraints following the enterprise pattern.

        Args:
            prompt_content: The prompt to send to Claude
            mcp_config: Path to MCP configuration
            allowed_tools: List of allowed MCP tools
            timeout: Execution timeout in seconds
            max_memory_mb: Maximum memory usage in MB
            max_output_mb: Maximum output size in MB
            working_directory: Working directory for execution
            env_vars: Additional environment variables
            stream_output: Whether to stream output for memory efficiency

        Returns:
            Execution result with metrics

        Raises:
            SubprocessTimeoutError: If timeout is reached
            SubprocessMemoryError: If memory limit is exceeded
            SubprocessError: For other execution errors

        """
        start_time = time.time()

        # Build command following the guide pattern:
        # claude --print --mcp-config mcp-config.json --allowedTools Read,Write,Edit,Bash < prompt.md
        cmd = [
            "claude",
            "--print",  # Non-interactive mode for programmatic use
            "--mcp-config",
            str(mcp_config),
            "--allowedTools",
            ",".join(allowed_tools),
        ]

        # Create environment
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)

        # Add MCP-specific environment variables
        env["MCP_MAX_MEMORY_MB"] = str(max_memory_mb)
        env["MCP_TIMEOUT"] = str(timeout)

        # Set working directory
        cwd = str(working_directory) if working_directory else None

        logger.info(
            "Executing Claude CLI",
            command=" ".join(cmd),
            tools=allowed_tools,
            timeout=timeout,
            memory_limit=max_memory_mb,
            working_dir=cwd,
            stream_output=stream_output,
        )

        try:
            # Create process with prompt via stdin
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
                limit=(
                    max_output_mb * 1024 * 1024 if not stream_output else 1024 * 1024
                ),  # 1MB buffer for streaming
            )

            self._active_processes[process.pid] = process

            # Create process monitor
            monitor = ProcessMonitor(process.pid, max_memory_mb, max_output_mb * 1024 * 1024)

            # Create monitoring task
            monitor_task = asyncio.create_task(self._monitor_process(process, monitor, timeout))

            try:
                if stream_output:
                    # Stream output to prevent memory issues
                    stdout_chunks = []
                    stderr_chunks = []

                    # Send prompt
                    process.stdin.write(prompt_content.encode("utf-8"))
                    await process.stdin.drain()
                    process.stdin.close()

                    # Read output in chunks
                    async def read_stream(stream, chunks, max_size):
                        total_size = 0
                        while True:
                            chunk = await stream.read(8192)  # 8KB chunks
                            if not chunk:
                                break
                            total_size += len(chunk)
                            if total_size > max_size:
                                chunks.append(b"... [output truncated]")
                                break
                            chunks.append(chunk)

                    # Read both streams concurrently
                    await asyncio.gather(
                        read_stream(process.stdout, stdout_chunks, max_output_mb * 1024 * 1024),
                        read_stream(process.stderr, stderr_chunks, max_output_mb * 1024 * 1024),
                    )

                    # Wait for process to complete
                    await asyncio.wait_for(process.wait(), timeout=timeout)

                    # Combine chunks
                    stdout = b"".join(stdout_chunks).decode("utf-8", errors="replace")
                    stderr = b"".join(stderr_chunks).decode("utf-8", errors="replace")

                else:
                    # Non-streaming mode (original)
                    stdout_data, stderr_data = await asyncio.wait_for(
                        process.communicate(input=prompt_content.encode("utf-8")), timeout=timeout
                    )
                    stdout = stdout_data.decode("utf-8", errors="replace")
                    stderr = stderr_data.decode("utf-8", errors="replace")

                # Cancel monitoring
                monitor_task.cancel()
                try:
                    await monitor_task
                except asyncio.CancelledError:
                    pass

                # Get metrics
                metrics = monitor.get_metrics()

                # Log output preview
                logger.debug(
                    "Claude CLI output",
                    stdout_preview=stdout[:200] + "..." if len(stdout) > 200 else stdout,
                    stderr_preview=stderr[:200] + "..." if len(stderr) > 200 else stderr,
                    exit_code=process.returncode,
                )

                return CLIExecutionResult(
                    stdout=stdout,
                    stderr=stderr,
                    exit_code=process.returncode or 0,
                    execution_time=time.time() - start_time,
                    memory_peak_mb=metrics["memory_peak_mb"],
                    cpu_time=metrics["cpu_time"],
                    truncated=stream_output and "output truncated" in stdout,
                )

            except asyncio.TimeoutError:
                # Kill process on timeout
                await self._kill_process(process)

                return CLIExecutionResult(
                    stdout="",
                    stderr=f"Process timed out after {timeout} seconds",
                    exit_code=-1,
                    execution_time=timeout,
                    memory_peak_mb=monitor.memory_peak_mb,
                    cpu_time=monitor.cpu_time,
                    timeout_reached=True,
                )

        except Exception as e:
            logger.error("Failed to execute Claude CLI", error=str(e), exc_info=True)
            raise SubprocessError(f"Failed to execute Claude CLI: {str(e)}")

        finally:
            # Clean up
            if process.pid in self._active_processes:
                del self._active_processes[process.pid]

    async def _monitor_process(
        self, process: asyncio.subprocess.Process, monitor: ProcessMonitor, timeout: int
    ):
        """Monitor process for resource usage.

        Args:
            process: Process to monitor
            monitor: Process monitor instance
            timeout: Overall timeout in seconds

        """
        check_interval = 0.5  # Check every 500ms
        elapsed = 0.0

        while process.returncode is None and elapsed < timeout:
            # Check resource limits
            output_size = 0  # Would need to track actual output size
            limit_exceeded, reason = await monitor.check_limits(output_size)

            if limit_exceeded:
                logger.warning("Process limit exceeded", pid=process.pid, reason=reason)
                await self._kill_process(process)
                # Extract memory usage from reason
                import re

                match = re.search(r"(\d+\.?\d*)MB > (\d+)MB", reason)
                if match:
                    actual_mb = float(match.group(1))
                    limit_mb = int(match.group(2))
                    raise SubprocessMemoryError("claude", limit_mb, actual_mb)
                else:
                    raise SubprocessMemoryError("claude", max_memory_mb, 0.0)

            await asyncio.sleep(check_interval)
            elapsed += check_interval

    async def _kill_process(self, process: asyncio.subprocess.Process):
        """Kill a process and its children.

        Args:
            process: Process to kill

        """
        try:
            if process.returncode is None:
                # Try graceful termination first
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Force kill if graceful termination fails
                    process.kill()
                    await process.wait()

                logger.info(f"Process {process.pid} terminated")
        except Exception as e:
            logger.error(f"Failed to kill process {process.pid}: {e}")

    async def check_command_available(self, command: str) -> bool:
        """Check if a command is available in PATH.

        Args:
            command: Command to check

        Returns:
            True if command is available

        """
        try:
            process = await asyncio.create_subprocess_exec(
                "which", command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
            )

            stdout, _ = await process.communicate()
            return process.returncode == 0 and bool(stdout.strip())

        except Exception:
            return False

    async def cleanup(self):
        """Clean up any remaining processes."""
        for _pid, process in list(self._active_processes.items()):
            await self._kill_process(process)

        self._active_processes.clear()
        logger.info("SafeSubprocessManager cleaned up")


# Global instance
_subprocess_manager: Optional[SafeSubprocessManager] = None


def get_subprocess_manager() -> SafeSubprocessManager:
    """Get or create subprocess manager instance.

    Returns:
        Global subprocess manager instance

    """
    global _subprocess_manager
    if _subprocess_manager is None:
        _subprocess_manager = SafeSubprocessManager()
    return _subprocess_manager
