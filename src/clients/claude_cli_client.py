"""Claude CLI client for code generation tasks.

This module provides a wrapper around the Claude CLI for sub-agents
to use when generating code, tests, and documentation.
"""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from structlog import get_logger

from src.core.exceptions import APIError, APIResponseError


logger = get_logger(__name__)


class ClaudeCLIClient:
    """Wrapper for Claude CLI to generate code and documentation."""
    
    def __init__(self):
        """Initialize the Claude CLI client."""
        self.cli_command = "claude"  # Assumes claude is in PATH
        logger.info("Claude CLI client initialized")
    
    async def create_code(
        self,
        prompt: str,
        context_files: Optional[List[Path]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> str:
        """Generate code using Claude CLI.
        
        Args:
            prompt: The prompt for code generation
            context_files: Optional list of files to include as context
            max_tokens: Maximum tokens for response
            temperature: Temperature for generation
            
        Returns:
            Generated code as string
        """
        try:
            # Build command
            cmd_parts = [self.cli_command, "--print"]
            
            # Note: Claude CLI doesn't support --file option directly
            # We'll need to include file contents in the prompt if needed
            full_prompt = prompt
            if context_files:
                file_contents = []
                for file_path in context_files:
                    if file_path.exists():
                        try:
                            with open(file_path, 'r') as f:
                                content = f.read()
                                file_contents.append(f"File: {file_path.name}\n```\n{content}\n```")
                        except Exception as e:
                            logger.warning(f"Failed to read context file {file_path}: {e}")
                
                if file_contents:
                    full_prompt = "\n\n".join(file_contents) + "\n\n" + prompt
            
            # Add the prompt as the last argument
            cmd_parts.append(full_prompt)
            
            # Log the command (truncate prompt for logging)
            log_prompt = full_prompt[:100] + "..." if len(full_prompt) > 100 else full_prompt
            logger.info(
                "Executing Claude CLI",
                command=f'claude --print "{log_prompt}"',
                context_files_count=len(context_files) if context_files else 0
            )
            
            # Execute the command
            process = await asyncio.create_subprocess_exec(
                *cmd_parts,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                logger.error(
                    "Claude CLI failed",
                    return_code=process.returncode,
                    error=error_msg
                )
                raise APIResponseError(f"Claude CLI failed: {error_msg}")
            
            response = stdout.decode('utf-8')
            
            logger.info(
                "Claude CLI response received",
                response_length=len(response)
            )
            
            return response
                    
        except Exception as e:
            logger.error(
                "Failed to execute Claude CLI",
                error=str(e),
                exc_info=True
            )
            raise APIError(f"Claude CLI execution failed: {str(e)}")
    
    async def create_message_for_code(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "code",
        **kwargs
    ) -> Dict[str, Any]:
        """Compatibility method that mimics the API interface but uses CLI.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            task_type: Type of task (code, test, documentation)
            **kwargs: Additional parameters
            
        Returns:
            Response mimicking the API format
        """
        # Extract the last user message as the prompt
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            raise ValueError("No user message found")
        
        prompt = user_messages[-1]["content"]
        
        # Add task-specific instructions
        if task_type == "code":
            prompt = f"Generate production-ready code based on the following request. Include proper error handling and documentation.\n\n{prompt}"
        elif task_type == "test":
            prompt = f"Generate comprehensive test cases for the following code. Use appropriate testing frameworks and include edge cases.\n\n{prompt}"
        elif task_type == "documentation":
            prompt = f"Generate clear and comprehensive documentation for the following code. Include examples and API references.\n\n{prompt}"
        
        # Get response from CLI
        response_text = await self.create_code(
            prompt=prompt,
            context_files=kwargs.get("context_files"),
            max_tokens=kwargs.get("max_tokens", 4096),
            temperature=kwargs.get("temperature", 0.3)
        )
        
        # Wrap in API-like response format
        return {
            "content": [{
                "text": response_text,
                "type": "text"
            }],
            "model": "claude-cli",
            "usage": {
                "input_tokens": len(prompt.split()),  # Rough estimate
                "output_tokens": len(response_text.split())  # Rough estimate
            }
        }
    
    async def check_cli_available(self) -> bool:
        """Check if Claude CLI is available and working.
        
        Returns:
            True if CLI is available, False otherwise
        """
        try:
            # Try to run claude --help to check if it's available
            process = await asyncio.create_subprocess_exec(
                self.cli_command,
                "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Look for typical help output
                output = stdout.decode('utf-8').strip()
                if "usage:" in output.lower() or "commands:" in output.lower():
                    logger.info("Claude CLI available")
                    return True
                else:
                    logger.warning("Claude CLI output unexpected")
                    return False
            else:
                logger.warning("Claude CLI not functioning properly")
                return False
                
        except FileNotFoundError:
            logger.error("Claude CLI not found in PATH")
            return False
        except Exception as e:
            logger.error("Failed to check Claude CLI", error=str(e))
            return False
    
    async def close(self):
        """Close the client (no-op for CLI)."""
        logger.info("Claude CLI client closed")