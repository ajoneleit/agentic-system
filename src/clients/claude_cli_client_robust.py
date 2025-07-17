"""Claude Code client for code generation tasks - Robust version.

This module provides a wrapper around the Claude Code CLI for sub-agents
to use when generating code, tests, and documentation.

FIXED: Resolves OSError [Errno 7] "argument too long" by using temporary files
for large prompts and proper CLI argument handling.

Command format: claude -p "prompt" --output-format json
For large prompts: claude -p @filename --output-format json
"""

import asyncio
import json
import os
import tempfile
import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4
import atexit
import signal

from structlog import get_logger

from src.core.exceptions import APIError, APIResponseError


logger = get_logger(__name__)

# Track temp files for cleanup
_temp_files = set()

# Maximum output size in bytes (10MB)
MAX_OUTPUT_BYTES = 10 * 1024 * 1024


def _atomic_write_file(file_path: Path, content: str) -> Dict[str, Any]:
    """Write file atomically using .tmp and os.replace().
    
    Args:
        file_path: Path to write to
        content: Content to write
        
    Returns:
        Dict with file information
    """
    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check file size
    content_bytes = content.encode('utf-8')
    if len(content_bytes) > MAX_OUTPUT_BYTES:
        raise ValueError(f"File too large: {len(content_bytes)} bytes > {MAX_OUTPUT_BYTES}")
    
    # Write to temporary file
    tmp_path = file_path.with_suffix(file_path.suffix + '.tmp')
    
    try:
        with open(tmp_path, 'w', encoding='utf-8', newline='\n') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        
        # Atomic replace
        os.replace(tmp_path, file_path)
        
        # Calculate hash
        sha256_hash = hashlib.sha256(content_bytes).hexdigest()
        
        return {
            "path": str(file_path),
            "action": "created" if not file_path.exists() else "updated",
            "size_bytes": len(content_bytes),
            "sha256": sha256_hash
        }
        
    except Exception as e:
        # Clean up tmp file if it exists
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except:
                pass
        raise e


def _create_json_response(
    status: str = "ok",
    summary: str = "",
    files: Optional[List[Dict[str, Any]]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
    metrics: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Create a JSON response according to the protocol.
    
    Args:
        status: "ok" or "error"
        summary: One-line human summary
        files: List of file information
        errors: List of error information
        metrics: Metrics information
        
    Returns:
        JSON response dict
    """
    return {
        "status": status,
        "summary": summary,
        "files": files or [],
        "errors": errors or [],
        "metrics": metrics or {}
    }


def _create_error_dict(
    error_type: str,
    message: str,
    fatal: bool = False
) -> Dict[str, Any]:
    """Create an error dict according to the protocol.
    
    Args:
        error_type: Type of error (SyntaxError, RateLimit, FileTooLarge, Unknown)
        message: Human-readable error message
        fatal: Whether this is a fatal error
        
    Returns:
        Error dict
    """
    return {
        "type": error_type,
        "message": message,
        "fatal": fatal
    }


def _cleanup_temp_files():
    """Clean up any remaining temporary files."""
    for temp_file in list(_temp_files):
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                logger.debug(f"Cleaned up temp file: {temp_file}")
        except Exception as e:
            logger.warning(f"Failed to clean up temp file {temp_file}: {e}")
        finally:
            _temp_files.discard(temp_file)


# Register cleanup handlers
atexit.register(_cleanup_temp_files)
signal.signal(signal.SIGTERM, lambda signum, frame: _cleanup_temp_files())
signal.signal(signal.SIGINT, lambda signum, frame: _cleanup_temp_files())


class ClaudeCodeClient:
    """Wrapper for Claude Code to generate code and documentation.
    
    Uses the correct Claude Code format:
    - Small prompts: claude -p "prompt" --output-format json
    - Large prompts: claude -p @filename --output-format json
    """
    
    # Conservative limit for when to use temp files (in characters)
    # This accounts for shell environment variables and other overhead
    TEMP_FILE_THRESHOLD = 4000
    
    def __init__(self):
        """Initialize the Claude Code client.
        
        Claude Code always uses JSON output format for structured responses.
        """
        self.cli_command = "claude"  # Assumes claude is in PATH
        self.json_output = True  # Always use JSON output in this project
        logger.info("Claude Code client (robust version) initialized with JSON output")
    
    async def create_code(
        self,
        prompt: str,
        context_files: Optional[List[Path]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
        workspace_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Generate code using Claude Code.
        
        Args:
            prompt: The prompt for code generation
            context_files: Optional list of files to include as context
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            workspace_dir: Optional directory to run Claude in (where files will be written)
            
        Returns:
            JSON response (dict) with structured output from Claude Code
        """
        temp_file_path = None
        try:
            # Build the full prompt with context files if needed
            full_prompt = prompt
            if context_files:
                file_contents = []
                # Define ignored directories and extensions
                ignored_dirs = {".git", "__pycache__", "htmlcov", ".pytest_cache", "node_modules", ".venv", "venv"}
                ignored_extensions = {
                    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
                    ".pyc", ".pyo", ".pyd", ".so", ".o", ".a", ".dll", ".exe",
                    ".coverage", ".db", ".sqlite", ".log", ".zip", ".tar", ".gz"
                }

                for file_path in context_files:
                    # Skip ignored directories and file types
                    if any(part in ignored_dirs for part in file_path.parts):
                        continue
                    if file_path.suffix.lower() in ignored_extensions:
                        continue

                    if file_path.exists() and file_path.is_file():
                        try:
                            # Check file size to avoid reading huge files
                            file_size = file_path.stat().st_size
                            if file_size > 1_000_000:  # Skip files larger than 1MB
                                logger.warning(f"Skipping large file in context: {file_path} ({file_size} bytes)")
                                continue
                                
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            file_contents.append(f"File: {file_path.name}\n```\n{content}\n```")
                        except UnicodeDecodeError:
                            logger.warning(f"Skipping binary file in context: {file_path}")
                        except Exception as e:
                            logger.warning(f"Failed to read context file {file_path}: {e}")
                
                if file_contents:
                    full_prompt = "\n\n".join(file_contents) + "\n\n" + prompt
            
            # Determine whether to use temp file based on prompt size
            use_temp_file = len(full_prompt) > self.TEMP_FILE_THRESHOLD
            
            # Set up environment
            env = os.environ.copy()
            env['CLAUDE_HEADLESS'] = '1'  # Ensure headless mode
            
            # Set working directory if provided
            cwd = str(workspace_dir) if workspace_dir else None
            
            if use_temp_file:
                # Create a secure temporary file
                fd, temp_file_path = tempfile.mkstemp(suffix='.md', prefix='claude_prompt_', text=True)
                _temp_files.add(temp_file_path)
                
                try:
                    # Write prompt to temp file using the file descriptor
                    with os.fdopen(fd, 'w', encoding='utf-8') as temp_file:
                        temp_file.write(full_prompt)
                except Exception:
                    # If writing fails, ensure fd is closed
                    try:
                        os.close(fd)
                    except:
                        pass
                    raise
                
                # Build command using file input
                # Claude Code format: claude -p @filename --output-format json
                cmd_parts = [self.cli_command, "-p", f"@{temp_file_path}", "--output-format", "json"]
                
                logger.info(
                    "Executing Claude Code with temp file",
                    command=self.cli_command,
                    temp_file=temp_file_path,
                    workspace_dir=cwd or "current directory",
                    context_files_count=len(context_files) if context_files else 0,
                    prompt_length=len(full_prompt)
                )
                
                # Execute without stdin since we're using file input
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=cwd
                )
                
                # No stdin needed when using file input
                stdout, stderr = await process.communicate()
                
            else:
                # For smaller prompts, use command line argument
                # Claude Code format: claude -p "prompt" --output-format json
                cmd_parts = [self.cli_command, "-p", full_prompt, "--output-format", "json"]
                
                logger.info(
                    "Executing Claude Code with command line prompt",
                    command=self.cli_command,
                    workspace_dir=cwd or "current directory",
                    context_files_count=len(context_files) if context_files else 0,
                    prompt_length=len(full_prompt)
                )
                
                process = await asyncio.create_subprocess_exec(
                    *cmd_parts,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=cwd
                )
                
                # No stdin needed when using command line argument
                stdout, stderr = await process.communicate()
            
            # Check for errors
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') if stderr else "Unknown error"
                logger.error(
                    "Claude Code failed",
                    return_code=process.returncode,
                    error=error_msg,
                    stdout=stdout.decode('utf-8', errors='replace')[:500] if stdout else None
                )
                raise APIResponseError(
                    status_code=process.returncode,
                    response_body=error_msg,
                    reason=f"Claude Code failed with code {process.returncode}: {error_msg}"
                )
            
            response = stdout.decode('utf-8', errors='replace')
            
            # Handle empty response
            if not response.strip():
                logger.warning("Claude Code returned empty response")
                # Check stderr for any warnings
                if stderr:
                    logger.debug(f"CLI stderr: {stderr.decode('utf-8', errors='replace')}")
                
                # Always expect JSON output, empty response is an error
                raise APIResponseError(
                    status_code=200,
                    response_body="",
                    reason="Claude Code returned empty response"
                )
            
            # Always process response as JSON
            try:
                    json_response = json.loads(response)
                    
                    # Validate JSON response structure
                    if not isinstance(json_response, dict):
                        raise APIResponseError(
                            status_code=200,
                            response_body=response,
                            reason="Invalid JSON response format: expected object"
                        )
                    
                    # Check for required fields
                    required_fields = ["status", "summary", "files", "errors", "metrics"]
                    for field in required_fields:
                        if field not in json_response:
                            raise APIResponseError(
                                status_code=200,
                                response_body=response,
                                reason=f"Missing required field in JSON response: {field}"
                            )
                    
                    # Check for fatal errors
                    if json_response.get("status") == "error":
                        errors = json_response.get("errors", [])
                        fatal_errors = [e for e in errors if e.get("fatal", False)]
                        if fatal_errors:
                            error_msgs = [e.get("message", "Unknown error") for e in fatal_errors]
                            raise APIResponseError(
                                status_code=200,
                                response_body=response,
                                reason=f"Fatal errors in Claude Code response: {'; '.join(error_msgs)}"
                            )
                    
                    logger.info(
                        "Claude Code JSON response received",
                        response_length=len(response),
                        used_temp_file=use_temp_file,
                        status=json_response.get("status"),
                        files_count=len(json_response.get("files", [])),
                        errors_count=len(json_response.get("errors", []))
                    )
                    
                    return json_response
                    
            except json.JSONDecodeError as e:
                logger.error("Failed to parse JSON response from Claude Code", error=str(e))
                raise APIResponseError(
                    status_code=200,
                    response_body=response,
                    reason=f"Malformed JSON response from Claude Code: {str(e)}"
                )
                    
        except asyncio.TimeoutError:
            logger.error("Claude Code execution timed out")
            raise APIError("Claude Code execution timed out")
        except (APIResponseError, APIError) as e:
            # Re-raise API errors without wrapping
            raise
        except Exception as e:
            logger.error(
                "Failed to execute Claude Code",
                error=str(e),
                exc_info=True
            )
            raise APIError(f"Claude Code execution failed: {str(e)}")
        finally:
            # Clean up temp file if it exists
            if temp_file_path and temp_file_path in _temp_files:
                try:
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                    _temp_files.discard(temp_file_path)
                    logger.debug(f"Cleaned up temp file: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean up temp file: {e}")
    
    async def create_message_for_code(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "code",
        **kwargs
    ) -> Dict[str, Any]:
        """Direct Claude Code interface that returns structured JSON response.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            task_type: Type of task (code, test, documentation)
            **kwargs: Additional parameters
            
        Returns:
            JSON response (dict) - always returns structured JSON output
        """
        # Extract the last user message as the prompt
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            raise ValueError("No user message found")
        
        prompt = user_messages[-1]["content"]
        
        # Add task-specific instructions
        task_prompts = {
            "code": "Generate production-ready code based on the following request. Include proper error handling and documentation.",
            "test": "Generate comprehensive test cases for the following code. Use appropriate testing frameworks and include edge cases.",
            "documentation": "Generate clear and comprehensive documentation for the following code. Include examples and API references.",
        }
        
        task_instruction = task_prompts.get(task_type, "Complete the following task:")
        prompt = f"{task_instruction}\n\n{prompt}"
        
        # Get response from CLI - always returns JSON
        response = await self.create_code(
            prompt=prompt,
            context_files=kwargs.get("context_files"),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.3),
            workspace_dir=kwargs.get("workspace_dir")
        )
        
        # Return JSON response directly
        return response
    
    async def check_cli_available(self) -> bool:
        """Check if Claude Code is available and working.
        
        Returns:
            True if CLI is available, False otherwise
        """
        try:
            # Try to run claude --version or claude -h to check availability
            # Try --version first as it's typically faster
            for args in [["--version"], ["-h"], ["help"]]:
                try:
                    process = await asyncio.create_subprocess_exec(
                        self.cli_command,
                        *args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    
                    # Set a timeout for the check
                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(), 
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        try:
                            process.terminate()
                            await process.wait()
                        except:
                            pass
                        continue
                    
                    if process.returncode == 0:
                        output = stdout.decode('utf-8', errors='replace').strip()
                        # Check for typical output patterns
                        if any(keyword in output.lower() for keyword in ["claude", "version", "usage", "commands", "help"]):
                            logger.info(f"Claude Code available (checked with {' '.join([self.cli_command] + args)})")
                            return True
                except Exception:
                    continue
            
            logger.warning("Claude Code not functioning properly")
            return False
                
        except FileNotFoundError:
            logger.error("Claude Code not found in PATH")
            return False
        except Exception as e:
            logger.error(f"Failed to check Claude Code: {str(e)}")
            return False
    
    async def health_check(self) -> dict:
        """Perform health check with minimal API request.
        
        Returns:
            Dictionary with health check results
        """
        from anthropic import AsyncAnthropic
        from config import get_settings, ClaudeModel
        
        try:
            settings = get_settings()
            api_key = settings.api.key.get_secret_value()
            
            if not api_key:
                return {
                    "status": "error",
                    "message": "No API key configured"
                }
            
            # Create minimal API client for health check
            async with AsyncAnthropic(api_key=api_key) as client:
                response = await client.messages.create(
                    model=ClaudeModel.HAIKU.value,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=10,
                    temperature=0,
                )
                
                if response and response.content:
                    return {
                        "status": "ok",
                        "message": "Claude API connection successful",
                        "model": response.model,
                        "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
                    }
                else:
                    return {
                        "status": "error",
                        "message": "Unexpected API response format"
                    }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Health check failed: {str(e)}"
            }
    
    async def close(self):
        """Close the client and clean up resources."""
        _cleanup_temp_files()
        logger.info("Claude Code client closed")
    
    @classmethod
    def create_json_client(cls) -> 'ClaudeCodeClient':
        """Create a Claude Code client - always uses JSON output.
        
        Returns:
            ClaudeCodeClient instance (always with JSON output)
        """
        return cls()
    
    def is_json_output(self) -> bool:
        """Check if client is configured for JSON output.
        
        Returns:
            Always True - this client always uses JSON output
        """
        return True
    
    def convert_text_to_json_response(
        self, 
        text_response: str, 
        workspace_dir: Optional[Path] = None,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        elapsed_ms: int = 0
    ) -> Dict[str, Any]:
        """Convert a plain text response to JSON format.
        
        This method can be used to bridge existing plain text responses
        to the new JSON protocol format.
        
        Args:
            text_response: Plain text response from Claude Code
            workspace_dir: Workspace directory to scan for created files
            prompt_tokens: Number of prompt tokens used
            completion_tokens: Number of completion tokens used
            elapsed_ms: Elapsed time in milliseconds
            
        Returns:
            JSON response dict
        """
        files = []
        errors = []
        
        # If workspace_dir is provided, scan for files that might have been created
        if workspace_dir and workspace_dir.exists():
            try:
                # Simple heuristic: look for common code file extensions
                code_extensions = {'.py', '.js', '.ts', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb', '.php', '.cs'}
                for file_path in workspace_dir.rglob('*'):
                    if file_path.is_file() and file_path.suffix.lower() in code_extensions:
                        try:
                            content = file_path.read_text(encoding='utf-8')
                            content_bytes = content.encode('utf-8')
                            files.append({
                                "path": str(file_path.relative_to(workspace_dir)),
                                "action": "created",
                                "size_bytes": len(content_bytes),
                                "sha256": hashlib.sha256(content_bytes).hexdigest()
                            })
                        except Exception as e:
                            errors.append(_create_error_dict(
                                "Unknown",
                                f"Failed to read file {file_path}: {str(e)}",
                                fatal=False
                            ))
            except Exception as e:
                errors.append(_create_error_dict(
                    "Unknown",
                    f"Failed to scan workspace directory: {str(e)}",
                    fatal=False
                ))
        
        # Create metrics
        metrics = {
            "tokens_prompt": prompt_tokens,
            "tokens_completion": completion_tokens,
            "elapsed_ms": elapsed_ms
        }
        
        # Determine status
        status = "error" if any(e.get("fatal", False) for e in errors) else "ok"
        
        # Create summary
        if files:
            summary = f"Generated {len(files)} file(s)"
        elif text_response:
            summary = "Generated response"
        else:
            summary = "No output generated"
        
        return _create_json_response(
            status=status,
            summary=summary,
            files=files,
            errors=errors,
            metrics=metrics
        )


