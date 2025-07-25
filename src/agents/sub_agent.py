"""Base SubAgent implementation and specialized agent types.

This module provides the foundation for all sub-agents that execute specific
tasks under the coordination of the Meta Agent.
"""

import asyncio
import json
from abc import abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from structlog import get_logger

from config import ClaudeModel
from src.clients.claude_cli_client_robust import ClaudeCodeClient
from src.core.agent_errors import (
    AgentResultError,
    CLIError,
    CLINotAvailableError,
    CLIResponseError,
    DependencyError,
    WorkspaceError,
)
from src.core.communication import Message
from src.core.interfaces import (
    Agent,
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
)
from src.core.result import Result
from src.core.task_result import TaskResult
from src.core.workspace_index import WorkspaceIndex
from src.prompts.agent_prompts import get_agent_prompt
from src.utils.app_logging import log_execution_time
from src.utils.enhanced_monitoring import (
    LogLevel,
    log_agent_activity,
    log_progress_update,
)

# TEMP: Backward compatibility shim for test compatibility
try:
    from src.clients.health_client import ClaudeClient as _ClaudeClient

    ClaudeClient = _ClaudeClient  # TEMP shim for test compatibility
except ImportError:
    ClaudeClient = None  # Fallback if module doesn't exist

logger = get_logger(__name__)


class SubAgent(Agent):
    """Base class for all sub-agents in the system."""

    def __init__(self, agent_id: UUID, role: AgentRole):
        """Initialize sub-agent.

        Args:
            agent_id: Unique agent identifier
            role: Agent's specialized role

        """
        super().__init__(agent_id, role)
        self.claude_code_client: Optional[ClaudeCodeClient] = None
        self.context: Optional[TaskContext] = None
        self._is_initialized = False
        self._workspace_index: Optional[WorkspaceIndex] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._last_cli_response: Optional[str] = None  # Track CLI responses for debugging

        logger.info(
            "SubAgent created",
            agent_id=str(agent_id),
            role=role.value,
        )

    async def initialize(self, context: TaskContext) -> Result[None]:
        """Initialize agent with execution context.

        Args:
            context: Task execution context

        Returns:
            Result[None] indicating success or failure

        """
        try:
            self.context = context

            # Sub-agents ALWAYS use Claude Code
            self.claude_code_client = ClaudeCodeClient()

            # Check if CLI is available
            if not await self.claude_code_client.check_cli_available():
                return Result.failure(
                    CLINotAvailableError(
                        "Claude Code is required for sub-agents but is not available. "
                        "Please ensure 'claude' command is installed and in PATH.",
                        agent_id=self.id,
                    )
                )

            logger.info(
                "SubAgent initialized with Claude Code", agent_id=str(self.id), role=self.role.value
            )

            # Start message processing
            self._processing_task = asyncio.create_task(self._process_messages())

            self._is_initialized = True
            self.status = "idle"

            logger.info(
                "SubAgent initialized",
                agent_id=str(self.id),
                role=self.role.value,
            )

            return Result.success(None)

        except Exception as e:
            logger.error("Failed to initialize agent", agent_id=str(self.id), error=str(e))
            return Result.failure(
                AgentResultError(f"Agent initialization failed: {str(e)}", agent_id=self.id)
            )

    @abstractmethod
    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Execute the agent's specific task implementation.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            Result[List[Artifact]] containing artifacts or error

        """
        pass

    @log_execution_time("task_execution")
    async def execute_task(self, task: Task, context: TaskContext) -> Result[TaskResult]:
        """Execute a task and produce artifacts.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            Result[TaskResult] containing task result or error

        """
        # Validate agent is initialized
        if not self._is_initialized:
            return Result.failure(
                AgentResultError("Agent not initialized", agent_id=self.id, task_id=task.id)
            )

        self.current_task = task
        self.status = "working"

        # Initialize task result
        task_result = TaskResult(
            task_id=task.id, agent_id=self.id, success=True, start_time=datetime.now(timezone.utc)
        )

        try:
            logger.info(
                "Starting task execution",
                agent_id=str(self.id),
                task_id=str(task.id),
                task_name=task.name,
            )

            # Log task start with enhanced monitoring
            await log_agent_activity(
                agent_id=self.id,
                event_type="task_started",
                level=LogLevel.INFO,
                message=f"Starting task: {task.name}",
                task_id=str(task.id),
                task_name=task.name,
                task_type=task.type if hasattr(task, "type") else "unknown",
                agent_role=self.role.value,
            )

            # Update progress: Task started
            await log_progress_update(
                agent_id=self.id,
                operation="task_execution",
                progress_percentage=0.0,
                task_id=str(task.id),
                phase="initialization",
            )

            # Validate dependencies if context provides completed tasks
            if hasattr(context, "completed_tasks") and task.dependencies:
                await log_progress_update(
                    agent_id=self.id,
                    operation="dependency_validation",
                    progress_percentage=10.0,
                    task_id=str(task.id),
                    phase="dependency_check",
                )

                completed = getattr(context, "completed_tasks", set())
                if not task.is_ready(completed):
                    unsatisfied = [str(d) for d in task.dependencies if d not in completed]

                    # Log dependency failure
                    await log_agent_activity(
                        agent_id=self.id,
                        event_type="dependency_failed",
                        level=LogLevel.ERROR,
                        message=f"Task dependencies not satisfied: {len(unsatisfied)} unsatisfied",
                        task_id=str(task.id),
                        unsatisfied_dependencies=unsatisfied,
                    )

                    return Result.failure(
                        DependencyError(
                            f"Task '{task.name}' cannot execute - {len(unsatisfied)} dependencies not satisfied: {unsatisfied}",
                            agent_id=self.id,
                            task_id=task.id,
                            details={"unsatisfied_dependencies": unsatisfied},
                        )
                    )

            # Update progress: Dependencies validated
            await log_progress_update(
                agent_id=self.id,
                operation="task_execution",
                progress_percentage=20.0,
                task_id=str(task.id),
                phase="execution_starting",
            )

            # Execute the specific implementation
            artifacts_result = await self._execute_specific_task(task, context)

            if artifacts_result.is_failure():
                task_result.success = False
                task_result.add_error(str(artifacts_result.get_error()))
                task_result.end_time = datetime.now(timezone.utc)
                task_result.execution_time = (
                    task_result.end_time - task_result.start_time
                ).total_seconds()

                # Log task failure
                await log_agent_activity(
                    agent_id=self.id,
                    event_type="task_failed",
                    level=LogLevel.ERROR,
                    message=f"Task execution failed: {task.name}",
                    task_id=str(task.id),
                    task_name=task.name,
                    error=str(artifacts_result.get_error()),
                    execution_time=task_result.execution_time,
                    agent_role=self.role.value,
                )

                return Result.failure(artifacts_result.get_error())

            artifacts = artifacts_result.unwrap()

            # Update progress: Artifacts processing
            await log_progress_update(
                agent_id=self.id,
                operation="artifact_processing",
                progress_percentage=80.0,
                task_id=str(task.id),
                phase="storing_artifacts",
                artifacts_count=len(artifacts),
            )

            # Store artifacts using artifact manager if available
            if context.artifact_manager:
                for artifact in artifacts:
                    try:
                        # Store artifact in management system
                        stored = await context.artifact_manager.store_artifact(artifact)
                        task_result.add_artifact(
                            stored.id, is_primary=(len(task_result.artifacts) == 0)
                        )
                        self.produced_artifacts.append(stored.id)
                    except Exception as e:
                        logger.error(
                            "Failed to store artifact", artifact_name=artifact.name, error=str(e)
                        )
                        task_result.add_warning(
                            f"Failed to store artifact {artifact.name}: {str(e)}"
                        )
            else:
                # Fallback: just track artifact IDs
                for artifact in artifacts:
                    task_result.add_artifact(
                        artifact.id, is_primary=(len(task_result.artifacts) == 0)
                    )
                    self.produced_artifacts.append(artifact.id)

            # Record successful completion
            self.completed_tasks.append(task.id)
            task_result.end_time = datetime.now(timezone.utc)
            task_result.execution_time = (
                task_result.end_time - task_result.start_time
            ).total_seconds()

            # Update progress: Task completed
            await log_progress_update(
                agent_id=self.id,
                operation="task_completion",
                progress_percentage=100.0,
                task_id=str(task.id),
                phase="completed",
                artifacts_produced=len(artifacts),
            )

            logger.info(
                "Task completed successfully",
                agent_id=str(self.id),
                task_id=str(task.id),
                artifacts_produced=len(artifacts),
                execution_time=task_result.execution_time,
            )

            # Log task completion with enhanced monitoring
            await log_agent_activity(
                agent_id=self.id,
                event_type="task_completed",
                level=LogLevel.INFO,
                message=f"Task completed successfully: {task.name}",
                task_id=str(task.id),
                task_name=task.name,
                status="success",
                execution_time=task_result.execution_time,
                artifacts_produced=len(artifacts),
                agent_role=self.role.value,
                task_type=task.type if hasattr(task, "type") else "unknown",
            )

            return Result.success(task_result)

        except Exception as e:
            logger.error(
                "Task execution failed",
                agent_id=str(self.id),
                task_id=str(task.id),
                error=str(e),
                exc_info=True,
            )

            task_result.success = False
            task_result.add_error(str(e))
            task_result.end_time = datetime.now(timezone.utc)
            task_result.execution_time = (
                task_result.end_time - task_result.start_time
            ).total_seconds()

            # Log exception with enhanced monitoring
            await log_agent_activity(
                agent_id=self.id,
                event_type="task_exception",
                level=LogLevel.ERROR,
                message=f"Task execution threw exception: {task.name}",
                task_id=str(task.id),
                task_name=task.name,
                error=str(e),
                error_type=type(e).__name__,
                execution_time=task_result.execution_time,
                agent_role=self.role.value,
            )

            return Result.failure(
                AgentResultError(
                    f"Task execution failed: {str(e)}", agent_id=self.id, task_id=task.id
                )
            )

        finally:
            self.current_task = None
            self.status = "idle"

    async def _create_artifact(
        self,
        content: str,
        artifact_type: ArtifactType,
        name: str,
        task: Task,
        context: TaskContext,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Artifact:
        """Create an artifact with proper metadata.

        Args:
            content: Artifact content
            artifact_type: Type of artifact
            name: Artifact name
            task: Current task
            context: Task context
            metadata: Additional metadata

        Returns:
            Created artifact

        """
        # Use clean filename
        artifact_name = name

        # Ensure proper extension
        extension = self._get_file_extension(artifact_type, metadata)
        if extension and not artifact_name.endswith(extension):
            artifact_name += extension

        # Store metadata separately
        datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Create artifact
        artifact = Artifact(
            id=uuid4(),
            name=artifact_name,
            type=artifact_type,
            content=content,
            path=Path(artifact_name),
            language=metadata.get("language") if metadata else None,
            version=1,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            task_id=task.id,
            agent_id=self.id,
            tags={self.role.value, task.name},
            metadata={
                **context.artifact_metadata_template,
                **(metadata or {}),
                "agent_role": self.role.value,
                "project_id": context.project_id,
                "parent_task": str(context.parent_task_id) if context.parent_task_id else None,
            },
        )

        return artifact

    async def _write_to_workspace(
        self,
        filename: str,
        content: str,
        context: TaskContext,
        task: Task,
        artifact_type: ArtifactType = ArtifactType.SOURCE_CODE,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Artifact:
        """Write a file directly to the project workspace.

        Args:
            filename: Simple filename (e.g., "hello_world.py")
            content: File content
            context: Task context with workspace path
            task: Current task
            artifact_type: Type of artifact
            metadata: Additional metadata

        Returns:
            Created artifact

        """
        # Get workspace path from context
        workspace_path = Path(context.shared_memory.get("workspace_path", "."))

        # Write file to workspace
        file_path = workspace_path / filename
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        logger.info(
            "Wrote file to workspace", filename=filename, path=str(file_path), size=len(content)
        )

        # Update project files list in shared memory
        project_files = context.shared_memory.get("project_files", [])
        if filename not in project_files:
            project_files.append(filename)
            context.shared_memory["project_files"] = project_files

        # Create artifact record (but with simple name and workspace path)
        artifact = Artifact(
            id=uuid4(),
            name=filename,  # Use simple filename, not UUID-based name
            type=artifact_type,
            content=content,
            path=file_path,  # Actual workspace path
            language=metadata.get("language") if metadata else None,
            version=1,
            created_at=datetime.now(timezone.utc),
            modified_at=datetime.now(timezone.utc),
            task_id=task.id,
            agent_id=self.id,
            tags={self.role.value, task.name},
            metadata={
                **context.artifact_metadata_template,
                **(metadata or {}),
                "agent_role": self.role.value,
                "project_id": context.project_id,
                "workspace_file": True,  # Mark as workspace file
            },
        )

        # Store in artifact manager for versioning/tracking
        if context.artifact_manager:
            try:
                await context.artifact_manager.store_artifact(artifact)
            except Exception as e:
                logger.warning(
                    "Failed to store artifact in manager",
                    error=str(e),
                    artifact_id=str(artifact.id),
                )

        return artifact

    async def _read_from_workspace(self, filename: str, context: TaskContext) -> Optional[str]:
        """Read a file from the project workspace.

        Args:
            filename: Simple filename to read
            context: Task context with workspace path

        Returns:
            File content or None if not found

        """
        workspace_path = Path(context.shared_memory.get("workspace_path", "."))
        file_path = workspace_path / filename

        if file_path.exists():
            return file_path.read_text(encoding="utf-8")

        logger.warning("File not found in workspace", filename=filename, path=str(file_path))
        return None

    async def _update_artifact(
        self, artifact_id: UUID, new_content: str, reason: str, context: TaskContext
    ) -> Optional[Artifact]:
        """Update an existing artifact.

        Args:
            artifact_id: ID of artifact to update
            new_content: New content
            reason: Reason for update
            context: Task context

        Returns:
            Updated artifact or None if failed

        """
        if not context.artifact_manager:
            logger.warning("No artifact manager available for update")
            return None

        try:
            updated = await context.artifact_manager.update_artifact(
                artifact_id, new_content, reason=reason, metadata={"updated_by": str(self.id)}
            )
            return updated
        except Exception as e:
            logger.error("Failed to update artifact", artifact_id=str(artifact_id), error=str(e))
            return None

    async def _link_artifacts(
        self, primary: Artifact, dependency: Artifact, context: TaskContext
    ) -> None:
        """Link two artifacts as dependencies.

        Args:
            primary: Primary artifact
            dependency: Dependency artifact
            context: Task context

        """
        if not context.artifact_manager:
            return

        try:
            # Use dependency tracker if available
            if hasattr(context.artifact_manager, "_dependency_tracker"):
                tracker = context.artifact_manager._dependency_tracker
                await tracker.add_dependency(
                    primary.id,
                    dependency.id,
                    dependency_type="depends_on",
                    metadata={"linked_by": str(self.id)},
                )
            else:
                # Fallback: add to artifact metadata
                primary.dependencies.append(dependency.id)
                dependency.dependent_artifacts.append(primary.id)
        except Exception as e:
            logger.error(
                "Failed to link artifacts",
                primary_id=str(primary.id),
                dependency_id=str(dependency.id),
                error=str(e),
            )

    async def _get_task_artifacts(self, task_id: UUID, context: TaskContext) -> list[Artifact]:
        """Get all artifacts for a task.

        Args:
            task_id: Task ID
            context: Task context

        Returns:
            List of artifacts

        """
        if not context.artifact_manager:
            return []

        try:
            return await context.artifact_manager.get_artifacts_by_task(task_id)
        except Exception as e:
            logger.error("Failed to get task artifacts", task_id=str(task_id), error=str(e))
            return []

    def _get_file_extension(
        self, artifact_type: ArtifactType, metadata: Optional[dict[str, Any]] = None
    ) -> str:
        """Get appropriate file extension for artifact type.

        Args:
            artifact_type: Type of artifact
            metadata: Artifact metadata

        Returns:
            File extension with dot (e.g., ".py")

        """
        language = metadata.get("language") if metadata else None

        if artifact_type == ArtifactType.SOURCE_CODE:
            language_extensions = {
                "python": ".py",
                "javascript": ".js",
                "typescript": ".ts",
                "java": ".java",
                "go": ".go",
                "rust": ".rs",
                "cpp": ".cpp",
                "c": ".c",
            }
            return language_extensions.get(language, ".txt")
        elif artifact_type == ArtifactType.TEST_CODE:
            if language == "python":
                return "_test.py"
            elif language in ["javascript", "typescript"]:
                return ".test.js" if language == "javascript" else ".test.ts"
            else:
                return f"_test{self._get_file_extension(ArtifactType.SOURCE_CODE, metadata)}"
        elif artifact_type == ArtifactType.DOCUMENTATION:
            return ".md"
        elif artifact_type == ArtifactType.CONFIGURATION:
            return ".json"
        elif artifact_type == ArtifactType.BUILD_OUTPUT:
            return ".log"
        else:
            return ".txt"

    async def collaborate(self, other_agent: Agent, message: dict[str, Any]) -> dict[str, Any]:
        """Handle collaboration messages from other agents.

        Args:
            other_agent: Agent sending the message
            message: Communication message

        Returns:
            Response message

        """
        # Convert dict to Message object if needed
        if isinstance(message, dict):
            msg = Message(**message)
        else:
            msg = message

        # Queue message for processing
        await self._message_queue.put(msg)

        # Return acknowledgment
        return {
            "acknowledged": True,
            "agent_id": str(self.id),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _get_workspace_index(self, workspace_dir: Path) -> WorkspaceIndex:
        """Get or create workspace index for the given directory.

        Args:
            workspace_dir: Directory to index

        Returns:
            WorkspaceIndex instance

        """
        if self._workspace_index is None or self._workspace_index.root_path != workspace_dir:
            self._workspace_index = WorkspaceIndex(
                root_path=workspace_dir,
                ignore_patterns={".git", "__pycache__", "*.pyc", "*.pyo", ".DS_Store"},
            )
            self._workspace_index.build_index()
        return self._workspace_index

    async def _process_messages(self) -> None:
        """Process incoming messages asynchronously."""
        while True:
            try:
                message = await self._message_queue.get()
                await self._handle_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(
                    "Error processing message",
                    agent_id=str(self.id),
                    error=str(e),
                )

    async def _handle_message(self, message: Message) -> None:
        """Handle a specific message.

        Args:
            message: Message to handle

        """
        logger.debug(
            "Handling message",
            agent_id=str(self.id),
            message_type=message.message_type.value,
            sender_id=str(message.sender_id),
        )

        # Override in subclasses for specific handling
        pass

    async def _query_claude(
        self,
        prompt: str,
        model: Optional[ClaudeModel] = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        task_type: str = "code",
        context_files: Optional[list[Path]] = None,
    ) -> Result[str]:
        """Query Claude with a prompt using CLI.

        Args:
            prompt: User prompt
            model: Claude model to use (ignored for CLI)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            system_prompt: System prompt
            task_type: Type of task for CLI (code, test, documentation)
            context_files: Optional files to include as context for CLI

        Returns:
            Result[str] containing Claude's response or error

        """
        if not self.claude_code_client:
            return Result.failure(CLIError("Claude Code client not initialized", agent_id=self.id))

        # Use CLI for code generation
        if system_prompt:
            prompt = f"{system_prompt}\n\n{prompt}"

        logger.debug(
            "Using Claude Code",
            task_type=task_type,
            prompt_length=len(prompt),
            context_files=len(context_files) if context_files else 0,
        )

        # Get workspace directory from context
        workspace_dir = None
        if self.context and hasattr(self.context, "project_root"):
            workspace_dir = self.context.project_root / "workspace"
            workspace_dir.mkdir(parents=True, exist_ok=True)

        try:
            response = await self.claude_code_client.create_message_for_code(
                messages=[{"role": "user", "content": prompt}],
                task_type=task_type,
                temperature=temperature,
                max_tokens=max_tokens,
                context_files=context_files,
                workspace_dir=workspace_dir,
            )

            # Extract response content from Claude Code JSON response
            if isinstance(response, dict):
                # Claude Code returns JSON with format: {"type": "result", "result": "...", ...}
                cli_response = response.get("result", str(response))
            else:
                cli_response = response if isinstance(response, str) else str(response)

            self._last_cli_response = cli_response

            if not cli_response.strip():
                logger.error("Empty CLI response", response=response)
                return Result.failure(
                    CLIResponseError(
                        "Received empty response from Claude Code",
                        agent_id=self.id,
                        details={"response": response},
                    )
                )

            return Result.success(cli_response)

        except Exception as e:
            logger.error(
                "Failed to query Claude Code", agent_id=str(self.id), error=str(e), exc_info=True
            )
            return Result.failure(CLIError(f"Claude Code query failed: {str(e)}", agent_id=self.id))

    async def shutdown(self) -> None:
        """Gracefully shutdown the agent."""
        logger.info(
            "Shutting down agent",
            agent_id=str(self.id),
            role=self.role.value,
        )

        # Cancel message processing
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass

        # Close Claude Code client
        if self.claude_code_client:
            await self.claude_code_client.close()

        self.status = "terminated"
        logger.info("Agent shutdown complete", agent_id=str(self.id))


class CodeGeneratorAgent(SubAgent):
    """Agent specialized in generating code."""

    def __init__(self, agent_id: UUID):
        """Initialize code generator agent."""
        super().__init__(agent_id, AgentRole.CORE_LOGIC)

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Generate code based on task specification.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            Result[List[Artifact]] containing code artifacts or error

        """
        # Get the code generation prompt
        prompt_template = get_agent_prompt(self.role, "main")

        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Create a more natural language representation of the task
        task_description = f"Task: {task.name}\n"
        task_description += f"Description: {task.description}\n"
        if "deliverable" in task_spec:
            task_description += f"Deliverable: {task_spec['deliverable']}\n"
        if "language" in task_spec:
            task_description += f"Language: {task_spec['language']}\n"
        if "frameworks" in task_spec:
            task_description += f"Frameworks: {', '.join(task_spec['frameworks'])}\n"

        prompt_vars = {
            "task_specification": task_description,
            "project_context": json.dumps(
                context.shared_memory.get("project_context", {}), indent=2
            ),
            "language": task_spec.get("language", "python"),
            "frameworks": json.dumps(task_spec.get("frameworks", []), indent=2),
            "style_guide": context.global_constraints.get("style_guide", "PEP 8"),
            "available_artifacts": json.dumps([str(aid) for aid in task.artifacts], indent=2),
        }

        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)

        # Add workspace directory instruction
        prompt = f"""You are an AI assistant that creates and modifies files in a workspace.

You are working in the directory: {workspace_dir}

Your task is to create the necessary files to complete the following task:
{task_description}

Do not generate any summary or explanation. Only create or modify the files as requested.
"""

        # Get context files from workspace (only actual files, not directories)
        context_files = None
        if workspace_dir.exists():
            # Get all relevant code files using WorkspaceIndex
            workspace_index = self._get_workspace_index(workspace_dir)
            context_files = []
            for ext in [
                ".py",
                ".js",
                ".ts",
                ".java",
                ".go",
                ".rs",
                ".cpp",
                ".c",
                ".h",
            ]:
                files = workspace_index.get_files_by_extension(ext)
                context_files.extend([workspace_dir / f.relative_path for f in files])
            if not context_files:
                context_files = None

        # Query Claude with workspace context
        response_result = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.3,  # Lower temperature for code generation
            task_type="code",
            context_files=context_files,
        )

        if response_result.is_failure():
            return Result.failure(response_result.get_error())

        response = response_result.unwrap()

        # When using CLI, Claude writes files directly to workspace
        # The response should be a summary of what was created
        logger.info(f"Claude Code response: {response[:500]}...")

        # Get list of files in workspace after Claude ran
        created_files = []
        # When using the CLI, we expect Claude to write files directly.
        # The response should be a simple confirmation.
        # We will then scan the workspace to find the created files.

        # Claude Code should write files directly to workspace
        # The response is a plain text summary of what was created

        # Use WorkspaceIndex for efficient file scanning
        workspace_index = WorkspaceIndex(
            root_path=workspace_dir, ignore_patterns={".git", "__pycache__", "*.pyc", "*.pyo"}
        )
        workspace_index.build_index()

        # Get all files created in the workspace
        all_files = workspace_index.get_all_files()
        for file_info in all_files:
            created_files.append(file_info.relative_path)

        logger.info(f"Files found in workspace after CLI run: {created_files}")

        # If no files were created, there was an error
        if not created_files:
            logger.error(f"No files created by Claude Code. Response: {response}")
            return Result.failure(
                WorkspaceError(
                    "Claude Code did not create any files in the workspace",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"response": response},
                )
            )

        # Create artifacts for each file created
        artifacts = []
        logger.debug(f"Creating artifacts for {len(created_files)} files: {created_files}")
        for filename in created_files:
            file_path = workspace_dir / filename
            if file_path.exists():
                try:
                    # Read the content that Claude wrote
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    logger.warning(f"Could not read file with utf-8 encoding, skipping: {filename}")
                    continue  # Skip this file and move to the next one
                except Exception as e:
                    logger.error(f"Failed to read file {filename}: {e}")
                    continue

                # Determine artifact type based on file extension
                if filename.endswith((".md", ".txt", ".rst")):
                    artifact_type = ArtifactType.DOCUMENTATION
                elif filename.endswith((".json", ".yaml", ".yml", ".toml", ".ini", ".cfg")):
                    artifact_type = ArtifactType.CONFIGURATION
                elif filename.endswith((".gitignore", "requirements.txt", "Makefile")):
                    artifact_type = ArtifactType.CONFIGURATION
                else:
                    artifact_type = ArtifactType.SOURCE_CODE

                # Determine language based on extension
                ext_to_lang = {
                    ".py": "python",
                    ".js": "javascript",
                    ".ts": "typescript",
                    ".java": "java",
                    ".go": "go",
                    ".rs": "rust",
                    ".cpp": "cpp",
                    ".c": "c",
                    ".md": "markdown",
                    ".json": "json",
                    ".yaml": "yaml",
                    ".yml": "yaml",
                }
                language = ext_to_lang.get(Path(filename).suffix, "text")

                # Create artifact record
                artifact = await self._create_artifact(
                    content=content,
                    artifact_type=artifact_type,
                    name=filename,
                    task=task,
                    context=context,
                    metadata={
                        "language": language,
                        "dependencies": [],
                        "notes": "",
                        "workspace_path": str(file_path),
                    },
                )
                artifacts.append(artifact)

        if not artifacts:
            # If no files were created, create a summary artifact
            artifact = await self._create_artifact(
                content=response,
                artifact_type=ArtifactType.DOCUMENTATION,
                name="execution_summary.txt",
                task=task,
                context=context,
                metadata={"response": response},
            )
            artifacts.append(artifact)

        return Result.success(artifacts)


class TestWriterAgent(SubAgent):
    """Agent specialized in writing tests."""

    def __init__(self, agent_id: UUID):
        """Initialize test writer agent."""
        super().__init__(agent_id, AgentRole.TESTING)

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Generate tests for code.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            List of test artifacts

        """
        # Get the test generation prompt
        prompt_template = get_agent_prompt(self.role, "main")

        # Get the code to test - first check if it's provided in metadata
        code_to_test = task.metadata.get("code_to_test", "")
        code_file = None
        workspace_dir = context.project_root / "workspace"

        if code_to_test:
            # Code was provided directly in task metadata
            logger.info("Using code_to_test from task metadata")
        else:
            # Need to find code in workspace
            # First check if a specific file is mentioned in the task
            task_spec = task.metadata.get("specification", {})

            # Try to find the file to test from task metadata or by looking for Python files
            if "deliverable" in task_spec:
                # Extract filename from deliverable description
                deliverable = task_spec["deliverable"]
                # IMPORTANT: Skip if the deliverable is the test file itself
                if ".py" in deliverable and not deliverable.startswith("test_"):
                    import re

                    match = re.search(r"(\w+\.py)", deliverable)
                    if match:
                        potential_file = match.group(1)
                        # Only use it if it's not a test file
                        if not potential_file.startswith("test_"):
                            code_file = potential_file

            # If no specific file, look for Python files in the workspace recursively
            logger.info(f"Looking for Python files in workspace: {workspace_dir}")

            if not code_file and workspace_dir.exists():
                # Use WorkspaceIndex to find Python files
                workspace_index = WorkspaceIndex(
                    root_path=workspace_dir,
                    ignore_patterns={"__pycache__", "*.pyc", "*.pyo", ".git"},
                )
                workspace_index.build_index()

                python_files = workspace_index.get_files_by_extension(".py")
                logger.info(f"Python files found: {[f.relative_path for f in python_files]}")

                for file_info in python_files:
                    if not file_info.name.startswith("test_"):
                        code_file = file_info.relative_path
                        logger.info(f"Selected file to test: {code_file}")
                        break
            else:
                if not workspace_dir.exists():
                    logger.error(f"Workspace directory does not exist: {workspace_dir}")

            if not code_file:
                # List what we found for debugging
                logger.error(
                    f"No Python file found in workspace. Workspace exists: {workspace_dir.exists()}"
                )
                if workspace_dir.exists():
                    workspace_index = self._get_workspace_index(workspace_dir)
                    all_files = workspace_index.get_all_files()
                    logger.error(f"All files in workspace: {[f.name for f in all_files]}")
                return Result.failure(
                    WorkspaceError(
                        "No Python file found in workspace to test",
                        agent_id=self.id,
                        task_id=task.id,
                        details={
                            "workspace_dir": str(workspace_dir),
                            "exists": workspace_dir.exists(),
                        },
                    )
                )

            # Read the code from workspace
            try:
                file_path = workspace_dir / code_file
                if file_path.exists():
                    code_to_test = file_path.read_text()
                else:
                    return Result.failure(
                        WorkspaceError(
                            f"File {code_file} not found in workspace",
                            agent_id=self.id,
                            task_id=task.id,
                            details={"file": code_file, "workspace_dir": str(workspace_dir)},
                        )
                    )
            except Exception as e:
                logger.error(f"Could not read {code_file}: {e}")
                return Result.failure(
                    WorkspaceError(
                        f"Could not read file {code_file} from workspace: {e}",
                        agent_id=self.id,
                        task_id=task.id,
                        details={"file": code_file, "error": str(e)},
                    )
                )

        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})

        # Create a natural language representation of the test task
        test_task_description = "Task: Write tests for the following code.\n"
        test_task_description += f"Code to test:\n```python\n{code_to_test}\n```\n"
        if "test_framework" in task_spec:
            test_task_description += f"Test Framework: {task_spec['test_framework']}\n"
        if "coverage_target" in task_spec:
            test_task_description += f"Coverage Target: {task_spec['coverage_target']}%\n"

        prompt_vars = {
            "code_to_test": code_to_test,
            "task_specification": test_task_description,
            "test_framework": task_spec.get("test_framework", "pytest"),
            "coverage_target": task_spec.get("coverage_target", 90),
            "project_context": json.dumps(
                context.shared_memory.get("project_context", {}), indent=2
            ),
        }

        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)

        # Get workspace directory
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Add workspace directory instruction
        prompt = f"""You are working in the directory: {workspace_dir}

Please create test files directly in this workspace directory. Test files should be named with the 'test_' prefix.

{prompt}"""

        # Query Claude with workspace context
        context_files = None
        if workspace_dir.exists():
            workspace_index = self._get_workspace_index(workspace_dir)
            all_files = workspace_index.get_all_files()
            context_files = [workspace_dir / f.relative_path for f in all_files]

        response_result = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.3,
            task_type="test",
            context_files=context_files,
        )

        if response_result.is_failure():
            return Result.failure(response_result.get_error())

        response = response_result.unwrap()

        # When using CLI, Claude writes test files directly
        files_created = []
        # Scan workspace for test files
        import os

        for file in os.listdir(workspace_dir):
            if file.startswith("test_") and file.endswith(".py"):
                files_created.append(file)

        logger.info(f"Test files found in workspace: {files_created}")

        if not files_created:
            logger.error(f"No test files created by Claude Code. Response: {response}")
            return Result.failure(
                WorkspaceError(
                    "Claude Code did not create any test files in the workspace",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"response": response},
                )
            )

        # Create artifacts for test files
        artifacts = []
        for filename in files_created:
            file_path = workspace_dir / filename
            if file_path.exists():
                content = file_path.read_text()

                # Get the tested artifact ID from task metadata
                tested_artifact_id = task.metadata.get("code_artifact_id")

                artifact = await self._create_artifact(
                    content=content,
                    artifact_type=ArtifactType.TEST_CODE,
                    name=filename,
                    task=task,
                    context=context,
                    metadata={
                        "language": task_spec.get("language", "python"),
                        "test_framework": task_spec.get("test_framework", "pytest"),
                        "test_count": "unknown",
                        "coverage_estimate": 0,
                        "notes": "",
                        "workspace_path": str(file_path),
                        "tested_file": code_file,
                        "tested_artifact_id": tested_artifact_id,
                    },
                )
                artifacts.append(artifact)

                # Link test artifact to code artifact if possible
                if tested_artifact_id and context.link_test_artifacts and context.artifact_manager:
                    try:
                        code_artifact = await context.artifact_manager.get_artifact(
                            UUID(tested_artifact_id)
                        )
                        if code_artifact:
                            await self._link_artifacts(artifact, code_artifact, context)
                            logger.info(
                                "Linked test artifact to code artifact",
                                test_id=str(artifact.id),
                                code_id=tested_artifact_id,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to link test artifact to code: {e}")

        if not artifacts:
            # Create summary artifact if no test files found
            artifact = await self._create_artifact(
                content=response,
                artifact_type=ArtifactType.DOCUMENTATION,
                name="test_execution_summary.txt",
                task=task,
                context=context,
                metadata={"response": response},
            )
            artifacts.append(artifact)

        return Result.success(artifacts)


class DocumentationAgent(SubAgent):
    """Agent specialized in creating documentation."""

    def __init__(self, agent_id: UUID):
        """Initialize documentation agent."""
        super().__init__(agent_id, AgentRole.DOCUMENTATION)

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Generate documentation for code.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            List of documentation artifacts

        """
        # Get the documentation prompt
        prompt_template = get_agent_prompt(self.role, "main")

        # Get the code to document
        code_to_document = task.metadata.get("code_to_document", "# Code placeholder")

        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})

        # Create a natural language representation of the documentation task
        doc_task_description = "Task: Create documentation for the following code.\n"
        doc_task_description += f"Code to document:\n```python\n{code_to_document}\n```\n"
        if "doc_type" in task_spec:
            doc_task_description += f"Documentation Type: {task_spec['doc_type']}\n"
        if "target_audience" in task_spec:
            doc_task_description += f"Target Audience: {task_spec['target_audience']}\n"
        if "doc_style" in task_spec:
            doc_task_description += f"Documentation Style: {task_spec['doc_style']}\n"

        prompt_vars = {
            "code_to_document": code_to_document,
            "task_specification": doc_task_description,
            "doc_type": task_spec.get("doc_type", "api"),
            "target_audience": task_spec.get("target_audience", "developers"),
            "project_context": json.dumps(
                context.shared_memory.get("project_context", {}), indent=2
            ),
            "doc_style": task_spec.get("doc_style", "sphinx"),
        }

        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)

        # Get workspace directory
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Add workspace directory instruction
        prompt = f"""You are working in the directory: {workspace_dir}

Please create documentation files directly in this workspace directory (e.g., README.md, API.md, etc.).

{prompt}"""

        # Query Claude with workspace context
        context_files = None
        if workspace_dir.exists():
            workspace_index = self._get_workspace_index(workspace_dir)
            all_files = workspace_index.get_all_files()
            context_files = [workspace_dir / f.relative_path for f in all_files]

        response_result = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.5,
            task_type="documentation",
            context_files=context_files,
        )

        if response_result.is_failure():
            return Result.failure(response_result.get_error())

        response = response_result.unwrap()

        # Claude has written documentation files directly
        # Create a summary artifact
        artifact = await self._create_artifact(
            content=response,
            artifact_type=ArtifactType.DOCUMENTATION,
            name="documentation_summary.txt",
            task=task,
            context=context,
            metadata={
                "doc_type": task_spec.get("doc_type", "api"),
                "target_audience": task_spec.get("target_audience", "developers"),
                "workspace_path": str(workspace_dir),
                "language": "markdown",
            },
        )

        return Result.success([artifact])


class RefactorAgent(SubAgent):
    """Agent specialized in code refactoring and optimization."""

    def __init__(self, agent_id: UUID):
        """Initialize refactor agent."""
        super().__init__(agent_id, AgentRole.OPTIMIZATION)

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Refactor and optimize code.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            List of refactored code artifacts

        """
        # Get the refactoring prompt
        prompt_template = get_agent_prompt(self.role, "main")

        # Get the code to refactor
        code_to_refactor = task.metadata.get("code_to_refactor", "# Code placeholder")

        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})

        # Create a natural language representation of the refactoring task
        refactor_task_description = "Task: Refactor the following code.\n"
        refactor_task_description += f"Code to refactor:\n```python\n{code_to_refactor}\n```\n"
        if "refactoring_goals" in task_spec:
            refactor_task_description += (
                f"Refactoring Goals: {', '.join(task_spec['refactoring_goals'])}\n"
            )
        if "constraints" in task_spec:
            refactor_task_description += f"Constraints: {', '.join(task_spec['constraints'])}\n"

        prompt_vars = {
            "code_to_refactor": code_to_refactor,
            "task_specification": refactor_task_description,
            "refactoring_goals": json.dumps(
                task_spec.get("refactoring_goals", ["improve readability", "optimize performance"]),
                indent=2,
            ),
            "constraints": json.dumps(
                task_spec.get("constraints", ["maintain backward compatibility"]), indent=2
            ),
            "project_context": json.dumps(
                context.shared_memory.get("project_context", {}), indent=2
            ),
        }

        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)

        # Query Claude
        # Get workspace directory
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Add workspace directory instruction
        prompt = f"You are working in the directory: {workspace_dir}\n\n{prompt}"

        # Query Claude with workspace context
        context_files = None
        if workspace_dir.exists():
            workspace_index = self._get_workspace_index(workspace_dir)
            all_files = workspace_index.get_all_files()
            context_files = [workspace_dir / f.relative_path for f in all_files]

        response_result = await self._query_claude(
            prompt,
            model=ClaudeModel.OPUS,
            temperature=0.3,
            task_type="code",
            context_files=context_files,
        )

        if response_result.is_failure():
            return Result.failure(response_result.get_error())

        response = response_result.unwrap()

        # Claude has refactored code directly in workspace
        # Create a summary artifact
        artifact = await self._create_artifact(
            content=response,
            artifact_type=ArtifactType.SOURCE_CODE,
            name="refactoring_summary.txt",
            task=task,
            context=context,
            metadata={
                "refactoring_goals": task.metadata.get("specification", {}).get(
                    "refactoring_goals", ""
                ),
                "workspace_path": str(workspace_dir),
            },
        )

        return Result.success([artifact])


class DebugAgent(SubAgent):
    """Agent specialized in debugging and fixing issues."""

    def __init__(self, agent_id: UUID):
        """Initialize debug agent."""
        super().__init__(agent_id, AgentRole.VERIFICATION)

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Debug and fix code issues.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            List of fixed code artifacts

        """
        # Get the debug analysis prompt
        prompt_template = get_agent_prompt(self.role, "main")

        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})
        prompt_vars = {
            "problematic_code": task_spec.get("problematic_code", "# Code with issues"),
            "error_info": json.dumps(task_spec.get("error_info", {}), indent=2),
            "expected_behavior": task_spec.get("expected_behavior", ""),
            "actual_behavior": task_spec.get("actual_behavior", ""),
            "project_context": json.dumps(
                context.shared_memory.get("project_context", {}), indent=2
            ),
        }

        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)

        # Query Claude
        response_result = await self._query_claude(
            prompt,
            model=ClaudeModel.OPUS,  # Use Opus for complex debugging
            temperature=0.2,  # Lower temperature for precise fixes
            task_type="code",
        )

        if response_result.is_failure():
            return Result.failure(response_result.get_error())

        response = response_result.unwrap()

        # Parse response
        try:
            # Check if response is empty
            if not response or not response.strip():
                logger.error("Empty response from Claude", response=response)
                return Result.failure(
                    CLIResponseError(
                        "Received empty response from Claude",
                        agent_id=self.id,
                        task_id=task.id,
                        details={"response": response},
                    )
                )

            result = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse JSON response",
                response_preview=response[:500] if response else "empty",
                error=str(e),
            )
            import re

            json_match = re.search(r"\{.*\}", response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Try to fix common JSON issues with code
                    fixed_json = json_match.group()
                    # Replace unescaped newlines in strings
                    fixed_json = re.sub(
                        r'("(?:[^"\\]|\\.)*?")',
                        lambda m: m.group(0).replace("\n", "\\n").replace("\r", "\\r"),
                        fixed_json,
                    )
                    try:
                        result = json.loads(fixed_json)
                        logger.warning("Fixed malformed JSON from Claude")
                    except json.JSONDecodeError:
                        return Result.failure(
                            CLIResponseError(
                                f"Failed to parse Claude response as JSON. Response: {response[:500]}...",
                                agent_id=self.id,
                                task_id=task.id,
                                details={"response": response},
                            )
                        )
            else:
                return Result.failure(
                    CLIResponseError(
                        f"Failed to parse Claude response as JSON. Response: {response[:500]}...",
                        agent_id=self.id,
                        task_id=task.id,
                        details={"response": response},
                    )
                )

        # Get the recommended solution
        solutions = result.get("solutions", [])
        if not solutions:
            return Result.failure(
                AgentResultError(
                    "No solutions provided",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"result": result},
                )
            )

        recommended_idx = result.get("recommended_solution", 0)
        solution = solutions[recommended_idx]

        # Create fixed artifact using helper method
        artifact = await self._create_artifact(
            content=solution["code_fix"],
            artifact_type=ArtifactType.SOURCE_CODE,
            name=result.get("filename", "fixed_code.py"),
            task=task,
            context=context,
            metadata={
                "language": task_spec.get("language", "python"),
                "error_type": task_spec.get("error_info", {}).get("type", "unknown"),
                "diagnosis": result.get("diagnosis", {}),
                "solution": solution,
                "prevention": result.get("prevention", {}),
                "fix_confidence": solution.get("confidence", 0.0),
                "test_recommendations": result.get("test_recommendations", []),
            },
        )

        # If debugging an existing artifact, link the fixed version
        problematic_artifact_id = task.metadata.get("problematic_artifact_id")
        if problematic_artifact_id and context.artifact_manager:
            try:
                problematic_artifact = await context.artifact_manager.get_artifact(
                    UUID(problematic_artifact_id)
                )
                if problematic_artifact:
                    await self._link_artifacts(artifact, problematic_artifact, context)
            except Exception as e:
                logger.warning(f"Failed to link to problematic artifact: {e}")

        return Result.success([artifact])
