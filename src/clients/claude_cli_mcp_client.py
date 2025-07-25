"""Enhanced Claude CLI client with MCP (Model Context Protocol) support.

This module provides a drop-in replacement for the Claude API client that uses
the Claude CLI with MCP servers for enhanced capabilities like file operations,
command execution, and git integration.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from structlog import get_logger

from config import get_settings
from src.utils.subprocess_manager import CLIExecutionResult, SafeSubprocessManager

logger = get_logger(__name__)


class MCPToolUsage:
    """Tracks MCP tool usage during execution."""

    def __init__(self):
        self.tool_calls: list[dict[str, Any]] = []
        self.file_operations: list[dict[str, Any]] = []
        self.command_executions: list[dict[str, Any]] = []

    def add_tool_call(self, tool: str, operation: str, args: dict[str, Any], result: Any):
        """Record a tool call."""
        self.tool_calls.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "tool": tool,
                "operation": operation,
                "args": args,
                "result": result,
            }
        )

        # Categorize specific operations
        if tool == "filesystem":
            self.file_operations.append(
                {
                    "operation": operation,
                    "path": args.get("path", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
        elif tool == "bash":
            self.command_executions.append(
                {
                    "command": args.get("command", ""),
                    "exit_code": result.get("exit_code", -1),
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )


class PromptBuilder:
    """Builds MCP-aware prompts with tool instructions."""

    def build_mcp_prompt(
        self,
        base_prompt: str,
        agent_role: str,
        allowed_tools: list[str],
        workspace_path: Path,
        context_files: Optional[list[Path]] = None,
        task_metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Build a prompt with MCP tool instructions.

        Args:
            base_prompt: The original task prompt
            agent_role: Role of the agent (core_logic, testing, etc.)
            allowed_tools: List of allowed MCP tools
            workspace_path: Path to the agent's workspace
            context_files: Optional files to include as context
            task_metadata: Optional task metadata

        Returns:
            Enhanced prompt with MCP instructions

        """
        prompt_parts = []

        # Add MCP tool instructions
        prompt_parts.append("You have access to the following MCP tools:")
        prompt_parts.append("")

        tool_descriptions = {
            "filesystem:read": "Read files using the filesystem tool",
            "filesystem:write": "Write new files using the filesystem tool",
            "filesystem:edit": "Edit existing files using the filesystem tool",
            "filesystem:list": "List directory contents using the filesystem tool",
            "bash:execute": "Execute commands using the bash tool",
            "git:status": "Check git status using the git tool",
            "git:diff": "View git differences using the git tool",
            "search:grep": "Search for patterns in files using the search tool",
            "search:find": "Find files by name using the search tool",
        }

        for tool in allowed_tools:
            if tool in tool_descriptions:
                prompt_parts.append(f"- {tool}: {tool_descriptions[tool]}")

        prompt_parts.append("")
        prompt_parts.append(f"Your workspace is: {workspace_path}")
        prompt_parts.append("All file operations should be relative to this workspace.")
        prompt_parts.append("")

        # Add context files if provided
        if context_files:
            prompt_parts.append("Context files:")
            for file_path in context_files:
                if file_path.exists():
                    try:
                        content = file_path.read_text(encoding="utf-8")
                        prompt_parts.append(f"\nFile: {file_path.name}")
                        prompt_parts.append("```")
                        prompt_parts.append(content)
                        prompt_parts.append("```")
                    except Exception as e:
                        logger.warning(f"Failed to read context file {file_path}: {e}")
            prompt_parts.append("")

        # Add role-specific instructions
        role_instructions = {
            "core_logic": "Generate clean, maintainable code with proper error handling and documentation.",
            "testing": "Create comprehensive tests with good coverage. Use the bash tool to run tests.",
            "documentation": "Write clear documentation with examples. Update existing docs if needed.",
            "optimization": "Analyze and optimize code for performance. Test changes with the bash tool.",
            "verification": "Verify code quality and test coverage. Use bash to run linters and tests.",
        }

        if agent_role in role_instructions:
            prompt_parts.append(role_instructions[agent_role])
            prompt_parts.append("")

        # Add the original prompt
        prompt_parts.append("Task:")
        prompt_parts.append(base_prompt)

        # Add output format instructions
        prompt_parts.append("")
        prompt_parts.append("Provide a structured response with:")
        prompt_parts.append("1. Your approach and reasoning")
        prompt_parts.append("2. The code/content you generate")
        prompt_parts.append("3. Any files created or modified")
        prompt_parts.append("4. Commands executed and their results")

        return "\n".join(prompt_parts)


class ClaudeCodeMCPClient:
    """Claude CLI client with MCP support - drop-in replacement for ClaudeClient."""

    def __init__(self):
        """Initialize the Claude CLI MCP client."""
        self.settings = get_settings()
        self.mcp_config_path = Path(self.settings.mcp_config_path)
        self.subprocess_manager = SafeSubprocessManager()
        self.prompt_builder = PromptBuilder()
        self._workspaces: dict[str, Path] = {}  # task_id -> workspace_path

        logger.info("Claude CLI MCP client initialized", mcp_config=str(self.mcp_config_path))

    async def create_message(
        self,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.0,
        system: Optional[str] = None,
        tools: Optional[list[str]] = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Create a message using Claude CLI with MCP - API compatible interface.

        This method maintains compatibility with the existing ClaudeClient API
        while using the CLI with MCP under the hood.

        Args:
            model: Model name (ignored - uses CLI default)
            messages: List of message dicts with 'role' and 'content'
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            system: System prompt
            tools: MCP tools to enable
            **kwargs: Additional parameters (workspace_path, agent_role, etc.)

        Returns:
            API-compatible response dictionary

        """
        # Extract user message
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            raise ValueError("No user message found")

        base_prompt = user_messages[-1]["content"]

        # Add system prompt if provided
        if system:
            base_prompt = f"{system}\n\n{base_prompt}"

        # Determine agent role and workspace
        agent_role = kwargs.get("agent_role", "core_logic")
        task_id = kwargs.get("task_id", str(uuid4()))
        workspace_path = await self._setup_workspace(task_id, kwargs.get("workspace_path"))

        # Determine allowed tools based on agent role
        if tools is None:
            tools = self._get_default_tools(agent_role)

        # Build MCP-aware prompt
        enhanced_prompt = self.prompt_builder.build_mcp_prompt(
            base_prompt=base_prompt,
            agent_role=agent_role,
            allowed_tools=tools,
            workspace_path=workspace_path,
            context_files=kwargs.get("context_files"),
            task_metadata=kwargs.get("task_metadata"),
        )

        # Execute via CLI with MCP
        result = await self.subprocess_manager.execute_claude_cli(
            prompt_content=enhanced_prompt,
            mcp_config=self.mcp_config_path,
            allowed_tools=tools,
            timeout=kwargs.get("timeout", 600),
            max_memory_mb=kwargs.get("max_memory_mb", 2048),
            working_directory=workspace_path,
        )

        # Parse and validate output
        parsed_output = await self._parse_cli_output(result, task_id)

        # Track tool usage
        tool_usage = await self._extract_tool_usage(result)

        # Return API-compatible response
        return {
            "content": [{"text": parsed_output["response"], "type": "text"}],
            "model": "claude-cli-mcp",
            "usage": {
                "input_tokens": len(enhanced_prompt.split()),
                "output_tokens": len(parsed_output["response"].split()),
            },
            "metadata": {
                "task_id": task_id,
                "workspace_path": str(workspace_path),
                "tool_usage": tool_usage.tool_calls,
                "files_created": parsed_output.get("files_created", []),
                "files_modified": parsed_output.get("files_modified", []),
                "commands_executed": parsed_output.get("commands_executed", []),
                "execution_time": result.execution_time,
                "memory_peak_mb": result.memory_peak_mb,
            },
        }

    async def _setup_workspace(self, task_id: str, base_path: Optional[Path] = None) -> Path:
        """Set up an isolated workspace for the task.

        Args:
            task_id: Unique task identifier
            base_path: Optional base path for workspace

        Returns:
            Path to the task workspace

        """
        if task_id in self._workspaces:
            return self._workspaces[task_id]

        # Create workspace directory
        base = base_path or Path(self.settings.storage.base_path) / "workspaces"
        workspace_path = base / f"task_{task_id}"
        workspace_path.mkdir(parents=True, exist_ok=True)

        # Copy any necessary template files
        templates_path = Path("templates")
        if templates_path.exists():
            for template in templates_path.glob("*"):
                if template.is_file():
                    shutil.copy2(template, workspace_path)

        self._workspaces[task_id] = workspace_path
        logger.info(f"Workspace created for task {task_id}: {workspace_path}")

        return workspace_path

    def _get_default_tools(self, agent_role: str) -> list[str]:
        """Get default MCP tools for an agent role.

        Args:
            agent_role: Role of the agent

        Returns:
            List of allowed tools

        """
        # Load from MCP config if available
        if self.mcp_config_path.exists():
            try:
                config = json.loads(self.mcp_config_path.read_text())
                permissions = config.get("agentPermissions", {})
                role_config = permissions.get(agent_role, {})
                return role_config.get("allowedTools", [])
            except Exception as e:
                logger.warning(f"Failed to load MCP config: {e}")

        # Fallback to defaults
        defaults = {
            "core_logic": ["filesystem:write", "filesystem:read", "filesystem:edit", "search:grep"],
            "testing": ["filesystem:write", "filesystem:read", "bash:execute", "search:grep"],
            "documentation": ["filesystem:write", "filesystem:read", "filesystem:edit"],
            "optimization": ["filesystem:read", "filesystem:edit", "search:grep", "bash:execute"],
            "verification": ["filesystem:read", "bash:execute", "search:grep"],
        }

        return defaults.get(agent_role, ["filesystem:read"])

    async def _parse_cli_output(self, result: CLIExecutionResult, task_id: str) -> dict[str, Any]:
        """Parse CLI output and extract structured information.

        Args:
            result: CLI execution result
            task_id: Task identifier

        Returns:
            Parsed output dictionary

        """
        output = result.stdout

        # Try to extract structured JSON response
        try:
            # Look for JSON blocks in the output
            import re

            json_matches = re.findall(r"```json\n(.*?)\n```", output, re.DOTALL)
            if json_matches:
                # Use the last JSON block as the main response
                parsed = json.loads(json_matches[-1])
                return {
                    "response": parsed.get("code", parsed.get("content", output)),
                    "files_created": parsed.get("files_created", []),
                    "files_modified": parsed.get("files_modified", []),
                    "commands_executed": parsed.get("commands_executed", []),
                    "reasoning": parsed.get("reasoning", ""),
                }
        except Exception as e:
            logger.warning(f"Failed to parse JSON from output: {e}")

        # Fallback: extract code blocks
        code_matches = re.findall(
            r"```(?:python|javascript|typescript|java|go)?\n(.*?)\n```", output, re.DOTALL
        )

        return {
            "response": code_matches[0] if code_matches else output,
            "files_created": [],
            "files_modified": [],
            "commands_executed": [],
            "reasoning": "",
        }

    async def _extract_tool_usage(self, result: CLIExecutionResult) -> MCPToolUsage:
        """Extract MCP tool usage from execution result.

        Args:
            result: CLI execution result

        Returns:
            Tool usage tracking object

        """
        usage = MCPToolUsage()

        # Parse tool calls from stderr (MCP servers log there)
        if result.stderr:
            lines = result.stderr.split("\n")
            for line in lines:
                try:
                    # Look for MCP tool call patterns
                    if "mcp-server" in line and "tool:" in line:
                        # Extract tool information
                        parts = line.split()
                        tool_info = {
                            "tool": parts[2] if len(parts) > 2 else "unknown",
                            "operation": parts[3] if len(parts) > 3 else "unknown",
                            "timestamp": datetime.utcnow().isoformat(),
                        }
                        usage.add_tool_call(
                            tool_info["tool"], tool_info["operation"], {}, {"logged": True}
                        )
                except Exception as e:
                    logger.debug(f"Failed to parse tool usage line: {e}")

        return usage

    async def check_cli_available(self) -> bool:
        """Check if Claude CLI is available and MCP is configured.

        Returns:
            True if CLI and MCP are available

        """
        # Check CLI availability
        cli_available = await self.subprocess_manager.check_command_available("claude")
        if not cli_available:
            logger.error("Claude CLI not found")
            return False

        # Check MCP config exists
        if not self.mcp_config_path.exists():
            logger.error(f"MCP config not found at {self.mcp_config_path}")
            return False

        # Check MCP servers are available
        try:
            config = json.loads(self.mcp_config_path.read_text())
            for server_name, server_config in config.get("mcpServers", {}).items():
                command = server_config.get("command", "")
                if not await self.subprocess_manager.check_command_available(command):
                    logger.warning(f"MCP server '{server_name}' command '{command}' not available")
        except Exception as e:
            logger.error(f"Failed to validate MCP config: {e}")
            return False

        logger.info("Claude CLI and MCP are available")
        return True

    async def cleanup_workspace(self, task_id: str):
        """Clean up a task's workspace.

        Args:
            task_id: Task identifier

        """
        if task_id in self._workspaces:
            workspace_path = self._workspaces[task_id]
            try:
                shutil.rmtree(workspace_path)
                del self._workspaces[task_id]
                logger.info(f"Cleaned up workspace for task {task_id}")
            except Exception as e:
                logger.error(f"Failed to cleanup workspace: {e}")

    async def close(self):
        """Close the client and cleanup resources."""
        # Cleanup all workspaces
        for task_id in list(self._workspaces.keys()):
            await self.cleanup_workspace(task_id)

        logger.info("Claude CLI MCP client closed")


# Backward compatibility alias
ClaudeCLIMCPClient = ClaudeCodeMCPClient
