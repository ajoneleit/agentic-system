"""Base SubAgent implementation and specialized agent types.

This module provides the foundation for all sub-agents that execute specific
tasks under the coordination of the Meta Agent.
"""

import asyncio
import json
from abc import abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from structlog import get_logger

from config import get_settings, ClaudeModel
from src.clients.claude_client import ClaudeClient
from src.clients.claude_cli_client import ClaudeCLIClient
from src.core.communication import Message, MessageType
from src.core.exceptions import (
    AgentError,
    TaskExecutionError,
)
from src.core.interfaces import (
    Agent,
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
    TaskStatus,
)
from src.core.task_result import TaskResult
from src.prompts.agent_prompts import get_agent_prompt
from src.utils.app_logging import log_execution_time


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
        self.claude_client: Optional[ClaudeClient] = None
        self.claude_cli_client: Optional[ClaudeCLIClient] = None
        self.use_cli: bool = False
        self.context: Optional[TaskContext] = None
        self._is_initialized = False
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._processing_task: Optional[asyncio.Task] = None
        self._last_cli_response: Optional[str] = None  # Track CLI responses for debugging
        
        logger.info(
            "SubAgent created",
            agent_id=str(agent_id),
            role=role.value,
        )
    
    async def initialize(self, context: TaskContext) -> None:
        """Initialize agent with execution context.
        
        Args:
            context: Task execution context
        """
        self.context = context
        
        # Initialize appropriate client based on agent role
        settings = get_settings()
        
        # Use CLI for code generation tasks, API for Meta Agent tasks
        if self.role in [AgentRole.CORE_LOGIC, AgentRole.TESTING, AgentRole.DOCUMENTATION, AgentRole.OPTIMIZATION]:
            self.claude_cli_client = ClaudeCLIClient()
            # Check if CLI is available
            if not await self.claude_cli_client.check_cli_available():
                logger.warning("Claude CLI not available, falling back to API")
                self.claude_client = ClaudeClient()
                self.use_cli = False
            else:
                self.claude_client = None  # Don't use API
                self.use_cli = True
        else:
            # For other roles, use API
            self.claude_client = ClaudeClient()
            self.claude_cli_client = None
            self.use_cli = False
        
        # Start message processing
        self._processing_task = asyncio.create_task(self._process_messages())
        
        self._is_initialized = True
        self.status = "idle"
        
        logger.info(
            "SubAgent initialized",
            agent_id=str(self.id),
            role=self.role.value,
            using_cli=self.use_cli,
        )
    
    @abstractmethod
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
        """Execute the agent's specific task implementation.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            List of produced artifacts
        """
        pass
    
    @log_execution_time("task_execution")
    async def execute_task(self, task: Task, context: TaskContext) -> TaskResult:
        """Execute a task and produce artifacts.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            TaskResult with produced artifacts
        """
        if not self._is_initialized:
            raise AgentError(
                self.id,
                "Agent not initialized"
            )
        
        self.current_task = task
        self.status = "working"
        
        # Initialize task result
        result = TaskResult(
            task_id=task.id,
            agent_id=self.id,
            success=True,
            start_time=datetime.now(timezone.utc)
        )
        
        try:
            logger.info(
                "Starting task execution",
                agent_id=str(self.id),
                task_id=str(task.id),
                task_name=task.name,
            )
            
            # Execute the specific implementation
            artifacts = await self._execute_specific_task(task, context)
            
            # Store artifacts using artifact manager if available
            if context.artifact_manager:
                for artifact in artifacts:
                    try:
                        # Store artifact in management system
                        stored = await context.artifact_manager.store_artifact(artifact)
                        result.add_artifact(stored.id, is_primary=(len(result.artifacts) == 0))
                        self.produced_artifacts.append(stored.id)
                    except Exception as e:
                        logger.error(
                            "Failed to store artifact",
                            artifact_name=artifact.name,
                            error=str(e)
                        )
                        result.add_warning(f"Failed to store artifact {artifact.name}: {str(e)}")
            else:
                # Fallback: just track artifact IDs
                for artifact in artifacts:
                    result.add_artifact(artifact.id, is_primary=(len(result.artifacts) == 0))
                    self.produced_artifacts.append(artifact.id)
            
            # Record successful completion
            self.completed_tasks.append(task.id)
            result.end_time = datetime.now(timezone.utc)
            result.execution_time = (result.end_time - result.start_time).total_seconds()
            
            logger.info(
                "Task completed successfully",
                agent_id=str(self.id),
                task_id=str(task.id),
                artifacts_produced=len(artifacts),
                execution_time=result.execution_time,
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "Task execution failed",
                agent_id=str(self.id),
                task_id=str(task.id),
                error=str(e),
                exc_info=True,
            )
            
            result.success = False
            result.add_error(str(e))
            result.end_time = datetime.now(timezone.utc)
            result.execution_time = (result.end_time - result.start_time).total_seconds()
            
            return result
            
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
        metadata: Optional[Dict[str, Any]] = None
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
        # Generate artifact name based on naming convention
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        artifact_name = context.artifact_naming_convention.format(
            task_name=task.name.replace(" ", "_"),
            agent_type=self.role.value,
            timestamp=timestamp,
            name=name
        )
        
        # Determine file extension based on type and language
        extension = self._get_file_extension(artifact_type, metadata)
        if extension and not artifact_name.endswith(extension):
            artifact_name += extension
        
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
            }
        )
        
        return artifact
    
    async def _write_to_workspace(
        self,
        filename: str,
        content: str,
        context: TaskContext,
        task: Task,
        artifact_type: ArtifactType = ArtifactType.SOURCE_CODE,
        metadata: Optional[Dict[str, Any]] = None
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
        file_path.write_text(content, encoding='utf-8')
        
        logger.info(
            "Wrote file to workspace",
            filename=filename,
            path=str(file_path),
            size=len(content)
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
            }
        )
        
        # Store in artifact manager for versioning/tracking
        if context.artifact_manager:
            try:
                await context.artifact_manager.store_artifact(artifact)
            except Exception as e:
                logger.warning(
                    "Failed to store artifact in manager",
                    error=str(e),
                    artifact_id=str(artifact.id)
                )
        
        return artifact
    
    async def _read_from_workspace(
        self,
        filename: str,
        context: TaskContext
    ) -> Optional[str]:
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
            return file_path.read_text(encoding='utf-8')
        
        logger.warning(
            "File not found in workspace",
            filename=filename,
            path=str(file_path)
        )
        return None
    
    async def _update_artifact(
        self,
        artifact_id: UUID,
        new_content: str,
        reason: str,
        context: TaskContext
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
                artifact_id,
                new_content,
                reason=reason,
                metadata={"updated_by": str(self.id)}
            )
            return updated
        except Exception as e:
            logger.error(
                "Failed to update artifact",
                artifact_id=str(artifact_id),
                error=str(e)
            )
            return None
    
    async def _link_artifacts(
        self,
        primary: Artifact,
        dependency: Artifact,
        context: TaskContext
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
            if hasattr(context.artifact_manager, '_dependency_tracker'):
                tracker = context.artifact_manager._dependency_tracker
                await tracker.add_dependency(
                    primary.id,
                    dependency.id,
                    dependency_type="depends_on",
                    metadata={"linked_by": str(self.id)}
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
                error=str(e)
            )
    
    async def _get_task_artifacts(
        self,
        task_id: UUID,
        context: TaskContext
    ) -> List[Artifact]:
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
            logger.error(
                "Failed to get task artifacts",
                task_id=str(task_id),
                error=str(e)
            )
            return []
    
    def _get_file_extension(
        self,
        artifact_type: ArtifactType,
        metadata: Optional[Dict[str, Any]] = None
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
    
    async def collaborate(self, other_agent: Agent, message: Dict[str, Any]) -> Dict[str, Any]:
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
        context_files: Optional[List[Path]] = None,
    ) -> str:
        """Query Claude with a prompt using CLI or API.
        
        Args:
            prompt: User prompt
            model: Claude model to use (ignored for CLI)
            max_tokens: Maximum response tokens
            temperature: Sampling temperature
            system_prompt: System prompt
            task_type: Type of task for CLI (code, test, documentation)
            context_files: Optional files to include as context for CLI
            
        Returns:
            Claude's response text
        """
        if self.use_cli and self.claude_cli_client:
            # Use CLI for code generation
            if system_prompt:
                prompt = f"{system_prompt}\n\n{prompt}"
            
            logger.debug(
                "Using Claude CLI",
                task_type=task_type,
                prompt_length=len(prompt),
                context_files=len(context_files) if context_files else 0
            )
                
            response = await self.claude_cli_client.create_message_for_code(
                messages=[{"role": "user", "content": prompt}],
                task_type=task_type,
                temperature=temperature,
                max_tokens=max_tokens,
                context_files=context_files,
            )
            # Track CLI response for debugging
            cli_response = response.get("content", [{}])[0].get("text", "")
            self._last_cli_response = cli_response
            
            if not cli_response:
                logger.error("Empty CLI response", response=response)
                raise ValueError("Received empty response from Claude CLI")
                
            return cli_response
        else:
            # Fall back to API
            if not self.claude_client:
                raise AgentError(self.id, "Claude client not initialized")
            
            settings = get_settings()
            model = model or settings.agent.default_model
            
            if system_prompt is None:
                system_prompt = f"You are a {self.role.value} agent in an autonomous coding system."
            
            logger.debug(
                "Using Claude API",
                model=model.value if hasattr(model, 'value') else model,
                prompt_length=len(prompt)
            )
            
            response = await self.claude_client.create_message(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
            )
            
            if not response or not hasattr(response, 'content') or not response.content:
                logger.error("Empty API response", response=response)
                raise ValueError("Received empty response from Claude API")
                
            api_response = response.content[0].text
            
            if not api_response:
                logger.error("Empty text in API response", response=response)
                raise ValueError("Received empty text from Claude API")
                
            return api_response
    
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
        
        # Close Claude client
        if self.claude_client:
            await self.claude_client.close()
        if self.claude_cli_client:
            await self.claude_cli_client.close()
        
        self.status = "terminated"
        logger.info("Agent shutdown complete", agent_id=str(self.id))


class CodeGeneratorAgent(SubAgent):
    """Agent specialized in generating code."""
    
    def __init__(self, agent_id: UUID):
        """Initialize code generator agent."""
        super().__init__(agent_id, AgentRole.CORE_LOGIC)
    
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
        """Generate code based on task specification.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            List of code artifacts
        """
        # Get the code generation prompt
        prompt_template = get_agent_prompt(self.role, "main")
        
        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        prompt_vars = {
            "task_specification": json.dumps(task_spec, indent=2),
            "project_context": json.dumps(context.shared_memory.get("project_context", {}), indent=2),
            "language": task_spec.get("language", "python"),
            "frameworks": json.dumps(task_spec.get("frameworks", []), indent=2),
            "style_guide": context.global_constraints.get("style_guide", "PEP 8"),
            "available_artifacts": json.dumps(
                [str(aid) for aid in task.artifacts],
                indent=2
            ),
        }
        
        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)
        
        # Add workspace directory instruction and explicit code generation request
        prompt = f"""You are working in the directory: {workspace_dir}

IMPORTANT: You cannot write files directly when using --print mode. Instead, please provide the complete code in code blocks with the filename specified.

Format your response like this:
```python
# filename: calculator.py
# Complete code here
```

{prompt}

Please provide the complete code implementation in code blocks. Do not ask for permission to write files."""
        
        # Get context files from workspace (only actual files, not directories)
        context_files = None
        if workspace_dir.exists():
            # Get all relevant code files
            context_files = []
            for pattern in ["*.py", "*.js", "*.ts", "*.java", "*.go", "*.rs", "*.cpp", "*.c", "*.h"]:
                context_files.extend(workspace_dir.glob(pattern))
            # Only include actual files, not directories
            context_files = [f for f in context_files if f.is_file()]
            if not context_files:
                context_files = None
        
        # Query Claude with workspace context
        response = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.3,  # Lower temperature for code generation
            task_type="code",
            context_files=context_files,
        )
        
        # Parse response to get summary of what was created
        # When using CLI with --print, we need to extract and write files ourselves
        summary = {}
        try:
            # Try to extract JSON summary from response
            import re
            json_match = re.search(r'\{[^{}]*"files_created"[^{}]*\}', response, re.DOTALL)
            if json_match:
                summary = json.loads(json_match.group())
        except:
            # If no JSON summary, that's okay - we'll check the workspace
            logger.debug("No JSON summary in response, checking workspace for created files")
        
        # When using CLI, extract code blocks and write them
        if self.use_cli and response:
            import re
            logger.debug(f"CLI Response preview: {response[:500]}...")
            
            files_found = False
            
            # First, check if the response is JSON with code field
            json_parsed = False
            try:
                json_response = json.loads(response.strip())
                logger.debug(f"Successfully parsed JSON response: {list(json_response.keys()) if isinstance(json_response, dict) else 'not a dict'}")
                if isinstance(json_response, dict) and "code" in json_response:
                    json_parsed = True
                    # Handle JSON response format
                    code = json_response.get("code", "")
                    filename = json_response.get("filename", f"{task.name.lower().replace(' ', '_')}.py")
                    
                    logger.info(f"Found JSON response with code field, filename: {filename}")
                    if code:
                        file_path = workspace_dir / filename
                        file_path.write_text(code.strip())
                        logger.info(f"Wrote file from CLI JSON response: {filename}")
                        if "files_created" not in summary:
                            summary["files_created"] = []
                        summary["files_created"].append(filename)
                        files_found = True
                        
                        # Update summary with other fields
                        if "dependencies" in json_response:
                            summary["dependencies"] = json_response["dependencies"]
                        if "notes" in json_response:
                            summary["notes"] = json_response["notes"]
                        if "complexity_score" in json_response:
                            summary["complexity_score"] = json_response["complexity_score"]
            except json.JSONDecodeError as e:
                # Not valid JSON, but might be a JSON-like response with unescaped newlines
                logger.debug(f"Initial JSON parse failed: {e}")
                
                # Try to extract code from malformed JSON response
                if response.strip().startswith('{') and '"code"' in response:
                    import re
                    # Try multiple patterns to extract code
                    patterns = [
                        # Pattern 1: "code": "..." with proper escaping
                        r'"code"\s*:\s*"((?:[^"\\]|\\.)*)"',
                        # Pattern 2: Multiline code block after "code":
                        r'"code"\s*:\s*"([^"]+)"',
                        # Pattern 3: Extract everything between "code": " and the next ",
                        r'"code"\s*:\s*"(.*?)",\s*"[^"]+"\s*:',
                    ]
                    
                    for pattern in patterns:
                        match = re.search(pattern, response, re.DOTALL)
                        if match:
                            code = match.group(1)
                            # Unescape any escaped quotes
                            code = code.replace('\\"', '"')
                            
                            # Try to get filename
                            filename_match = re.search(r'"filename"\s*:\s*"([^"]+)"', response)
                            filename = filename_match.group(1) if filename_match else f"{task.name.lower().replace(' ', '_')}.py"
                            
                            logger.info(f"Extracted code from malformed JSON, filename: {filename}")
                            file_path = workspace_dir / filename
                            file_path.write_text(code.strip())
                            logger.info(f"Wrote file from extracted JSON response: {filename}")
                            if "files_created" not in summary:
                                summary["files_created"] = []
                            summary["files_created"].append(filename)
                            files_found = True
                            json_parsed = True
                            break
                
                if not json_parsed:
                    logger.debug("Response is not JSON, checking for code blocks")
            
            # If not JSON or no files found yet, look for code blocks
            if not files_found:
                # Look for file creation patterns in the response
                # Pattern 1: ```python filename.py
                # Pattern 2: # filename.py followed by code
                # Pattern 3: File: filename.py followed by code
                # Pattern 4: "I'll create filename.py" followed by code
                
                # Extract code blocks with filenames
                code_patterns = [
                    # ```python filename.py
                    r'```(?:python)?\s+(\S+\.py)\n(.*?)```',
                    # File: filename.py
                    r'File:\s*(\S+\.py)\s*\n```(?:python)?\n(.*?)```',
                    # I'll create/write filename.py
                    r'(?:create|write|save)\s+(?:a\s+)?(?:file\s+)?(?:called\s+)?[`"]?(\S+\.py)[`"]?\s*(?:with)?.*?\n```(?:python)?\n(.*?)```',
                    # filename.py: followed by code
                    r'(\S+\.py):\s*\n```(?:python)?\n(.*?)```'
                ]
                
                for pattern in code_patterns:
                    matches = re.findall(pattern, response, re.DOTALL | re.MULTILINE | re.IGNORECASE)
                    for match in matches:
                        filename = match[0]
                        code = match[1]
                        if filename and code:
                            file_path = workspace_dir / filename
                            file_path.write_text(code.strip())
                            logger.info(f"Wrote file from CLI response: {filename}")
                            if "files_created" not in summary:
                                summary["files_created"] = []
                            summary["files_created"].append(filename)
                            files_found = True
                
                # If no files found with specific names, look for any code blocks
                if not files_found:
                    code_blocks = re.findall(r'```(?:python)?\n(.*?)```', response, re.DOTALL)
                    if code_blocks:
                        logger.info(f"Found {len(code_blocks)} code blocks without explicit filenames")
                        
                        # For each code block, try to determine a good filename
                        for i, code in enumerate(code_blocks):
                            # Skip empty or very short blocks
                            if len(code.strip()) < 10:
                                continue
                            
                            # Try to determine filename from code content or task
                            filename = None
                            
                            # First check if filename is specified in the code
                            filename_match = re.search(r'#\s*filename:\s*(\S+\.py)', code, re.IGNORECASE)
                            if filename_match:
                                filename = filename_match.group(1)
                                logger.info(f"Found filename in code comment: {filename}")
                            
                            # Check code content for class/function names
                            class_match = re.search(r'class\s+(\w+)', code) if not filename else None
                            func_match = re.search(r'def\s+(\w+)', code) if not filename else None
                            
                            if class_match:
                                class_name = class_match.group(1).lower()
                                filename = f"{class_name}.py"
                            elif func_match:
                                func_name = func_match.group(1).lower()
                                if func_name not in ['__init__', 'main']:
                                    filename = f"{func_name}.py"
                            
                            # Fall back to task-based naming
                            if not filename:
                                task_words = task.name.lower().split()
                                for word in ['calculator', 'fibonacci', 'todo', 'parser', 'api', 'server']:
                                    if word in task_words or word in response.lower():
                                        filename = f"{word}.py"
                                        break
                            
                            # Final fallback
                            if not filename:
                                filename = f"{task.name.lower().replace(' ', '_')}.py"
                                if i > 0:
                                    filename = filename.replace('.py', f'_{i}.py')
                            
                            # Write the code block
                            file_path = workspace_dir / filename
                            file_path.write_text(code.strip())
                            logger.info(f"Wrote extracted code to: {filename}")
                            if "files_created" not in summary:
                                summary["files_created"] = []
                            summary["files_created"].append(filename)
                            files_found = True
            
            if not files_found:
                logger.warning("No code blocks found in CLI response")
                logger.debug(f"Full response: {response}")
        
        # Find files created (based on summary or by scanning workspace)
        files_created = summary.get("files_created", [])
        
        # If using API and no files were created, extract code from response
        if not files_created and not self.use_cli:
            # Look for code blocks in the response
            import re
            code_blocks = re.findall(r'```(?:python)?\n(.*?)```', response, re.DOTALL)
            if code_blocks:
                # Write each code block to a file
                for i, code in enumerate(code_blocks):
                    # Try to determine filename from response or use default
                    if "fibonacci" in response.lower():
                        filename = "fibonacci.py" if i == 0 else f"fibonacci_{i}.py"
                    elif "calculator" in response.lower():
                        filename = "calculator.py" if i == 0 else f"calculator_{i}.py"
                    else:
                        filename = f"{task.name.lower().replace(' ', '_')}.py"
                    
                    # Write code to file
                    file_path = workspace_dir / filename
                    file_path.write_text(code.strip())
                    files_created.append(filename)
                    logger.info(f"Extracted and wrote code to {filename}")
        
        if not files_created:
            # Scan workspace for new Python files
            import os
            for file in os.listdir(workspace_dir):
                if file.endswith(('.py', '.js', '.ts', '.java', '.go')):
                    files_created.append(file)
        
        # Create artifacts for each file created
        artifacts = []
        for filename in files_created:
            file_path = workspace_dir / filename
            if file_path.exists():
                # Read the content that Claude wrote
                content = file_path.read_text()
                
                # Create artifact record
                artifact = await self._create_artifact(
                    content=content,
                    artifact_type=ArtifactType.SOURCE_CODE,
                    name=filename,
                    task=task,
                    context=context,
                    metadata={
                        "language": task_spec.get("language", "python"),
                        "dependencies": summary.get("dependencies", []),
                        "notes": summary.get("notes", ""),
                        "workspace_path": str(file_path),
                    }
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
                metadata={"summary": summary}
            )
            artifacts.append(artifact)
        
        return artifacts


class TestWriterAgent(SubAgent):
    """Agent specialized in writing tests."""
    
    def __init__(self, agent_id: UUID):
        """Initialize test writer agent."""
        super().__init__(agent_id, AgentRole.TESTING)
    
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
        """Generate tests for code.
        
        Args:
            task: Task to execute
            context: Execution context
            
        Returns:
            List of test artifacts
        """
        # Get the test generation prompt
        prompt_template = get_agent_prompt(self.role, "main")
        
        # Get the code to test from workspace
        # First check if a specific file is mentioned in the task
        task_spec = task.metadata.get("specification", {})
        code_file = None
        
        # Try to find the file to test from task metadata or by looking for Python files
        if "deliverable" in task_spec:
            # Extract filename from deliverable description
            deliverable = task_spec["deliverable"]
            if ".py" in deliverable:
                import re
                match = re.search(r'(\w+\.py)', deliverable)
                if match:
                    code_file = match.group(1)
        
        # If no specific file, look for Python files in workspace directory
        workspace_dir = context.project_root / "workspace"
        logger.info(f"Looking for Python files in workspace: {workspace_dir}")
        
        if not code_file and workspace_dir.exists():
            import os
            files_in_workspace = os.listdir(workspace_dir)
            logger.info(f"Files in workspace: {files_in_workspace}")
            
            python_files = [f for f in files_in_workspace if f.endswith('.py')]
            logger.info(f"Python files found: {python_files}")
            
            for file in python_files:
                if not file.startswith('test_'):
                    code_file = file
                    logger.info(f"Selected file to test: {code_file}")
                    break
        else:
            if not workspace_dir.exists():
                logger.error(f"Workspace directory does not exist: {workspace_dir}")
            
        if not code_file:
            # List what we found for debugging
            logger.error(f"No Python file found in workspace. Workspace exists: {workspace_dir.exists()}")
            if workspace_dir.exists():
                all_files = list(workspace_dir.glob("*"))
                logger.error(f"All files in workspace: {[f.name for f in all_files]}")
            raise ValueError("No Python file found in workspace to test")
        
        # Read the code from workspace
        code_to_test = ""
        try:
            file_path = workspace_dir / code_file
            if file_path.exists():
                code_to_test = file_path.read_text()
            else:
                raise ValueError(f"File {code_file} not found in workspace")
        except Exception as e:
            logger.error(f"Could not read {code_file}: {e}")
            raise ValueError(f"Could not read file {code_file} from workspace: {e}")
        
        # Prepare prompt variables
        task_spec = task.metadata.get("specification", {})
        prompt_vars = {
            "code_to_test": code_to_test,
            "task_specification": json.dumps(task_spec, indent=2),
            "test_framework": task_spec.get("test_framework", "pytest"),
            "coverage_target": task_spec.get("coverage_target", 90),
            "project_context": json.dumps(context.shared_memory.get("project_context", {}), indent=2),
        }
        
        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)
        
        # Get workspace directory
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Add workspace directory instruction
        prompt = f"You are working in the directory: {workspace_dir}\n\n{prompt}"
        
        # Query Claude with workspace context
        response = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.3,
            task_type="test",
            context_files=[f for f in workspace_dir.glob("*") if f.is_file()] if workspace_dir.exists() else None,
        )
        
        # Parse response to get summary
        summary = {}
        try:
            import re
            json_match = re.search(r'\{[^{}]*"files_created"[^{}]*\}', response, re.DOTALL)
            if json_match:
                summary = json.loads(json_match.group())
        except:
            logger.debug("No JSON summary in response, checking workspace for test files")
        
        # Find test files created
        files_created = summary.get("files_created", [])
        if not files_created:
            # Scan workspace for test files
            import os
            for file in os.listdir(workspace_dir):
                if file.startswith("test_") and file.endswith(".py"):
                    files_created.append(file)
        
        # Create artifacts for test files
        artifacts = []
        for filename in files_created:
            file_path = workspace_dir / filename
            if file_path.exists():
                content = file_path.read_text()
                
                artifact = await self._create_artifact(
                    content=content,
                    artifact_type=ArtifactType.TEST_CODE,
                    name=filename,
                    task=task,
                    context=context,
                    metadata={
                        "language": task_spec.get("language", "python"),
                        "test_framework": task_spec.get("test_framework", "pytest"),
                        "test_count": summary.get("test_count", "unknown"),
                        "coverage_estimate": summary.get("coverage_estimate", 0),
                        "notes": summary.get("notes", ""),
                        "workspace_path": str(file_path),
                        "tested_file": code_file,
                    }
                )
                artifacts.append(artifact)
        
        if not artifacts:
            # Create summary artifact if no test files found
            artifact = await self._create_artifact(
                content=response,
                artifact_type=ArtifactType.DOCUMENTATION,
                name="test_execution_summary.txt",
                task=task,
                context=context,
                metadata={"summary": summary}
            )
            artifacts.append(artifact)
        
        return artifacts


class DocumentationAgent(SubAgent):
    """Agent specialized in creating documentation."""
    
    def __init__(self, agent_id: UUID):
        """Initialize documentation agent."""
        super().__init__(agent_id, AgentRole.DOCUMENTATION)
    
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
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
        prompt_vars = {
            "code_to_document": code_to_document,
            "doc_type": task_spec.get("doc_type", "api"),
            "target_audience": task_spec.get("target_audience", "developers"),
            "project_context": json.dumps(context.shared_memory.get("project_context", {}), indent=2),
            "doc_style": task_spec.get("doc_style", "sphinx"),
        }
        
        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)
        
        # Get workspace directory
        workspace_dir = context.project_root / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Add workspace directory instruction
        prompt = f"You are working in the directory: {workspace_dir}\n\n{prompt}"
        
        # Query Claude with workspace context
        response = await self._query_claude(
            prompt,
            model=ClaudeModel.SONNET,
            temperature=0.5,
            task_type="documentation",
            context_files=[f for f in workspace_dir.glob("*") if f.is_file()] if workspace_dir.exists() else None,
        )
        
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
                "workspace_path": str(workspace_dir)
            }
        )
        
        return [artifact]


class RefactorAgent(SubAgent):
    """Agent specialized in code refactoring and optimization."""
    
    def __init__(self, agent_id: UUID):
        """Initialize refactor agent."""
        super().__init__(agent_id, AgentRole.OPTIMIZATION)
    
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
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
        prompt_vars = {
            "code_to_refactor": code_to_refactor,
            "refactoring_goals": json.dumps(
                task_spec.get("refactoring_goals", ["improve readability", "optimize performance"]),
                indent=2
            ),
            "constraints": json.dumps(
                task_spec.get("constraints", ["maintain backward compatibility"]),
                indent=2
            ),
            "project_context": json.dumps(context.shared_memory.get("project_context", {}), indent=2),
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
        response = await self._query_claude(
            prompt,
            model=ClaudeModel.OPUS,
            temperature=0.3,
            task_type="code",
            context_files=[f for f in workspace_dir.glob("*") if f.is_file()] if workspace_dir.exists() else None,
        )
        
        # Claude has refactored code directly in workspace
        # Create a summary artifact
        artifact = await self._create_artifact(
            content=response,
            artifact_type=ArtifactType.SOURCE_CODE,
            name="refactoring_summary.txt",
            task=task,
            context=context,
            metadata={
                "refactoring_goals": task.metadata.get("specification", {}).get("refactoring_goals", ""),
                "workspace_path": str(workspace_dir)
            }
        )
        
        return [artifact]


class DebugAgent(SubAgent):
    """Agent specialized in debugging and fixing issues."""
    
    def __init__(self, agent_id: UUID):
        """Initialize debug agent."""
        super().__init__(agent_id, AgentRole.VERIFICATION)
    
    async def _execute_specific_task(
        self,
        task: Task,
        context: TaskContext
    ) -> List[Artifact]:
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
            "project_context": json.dumps(context.shared_memory.get("project_context", {}), indent=2),
        }
        
        # Generate the prompt
        prompt = prompt_template.render(**prompt_vars)
        
        # Query Claude
        response = await self._query_claude(
            prompt,
            model=ClaudeModel.OPUS,  # Use Opus for complex debugging
            temperature=0.2,  # Lower temperature for precise fixes
            task_type="code",
        )
        
        # Parse response
        try:
            # Check if response is empty
            if not response or not response.strip():
                logger.error("Empty response from Claude", response=response)
                raise ValueError("Received empty response from Claude")
                
            result = json.loads(response)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse JSON response",
                response_preview=response[:500] if response else "empty",
                error=str(e)
            )
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except json.JSONDecodeError:
                    # Try to fix common JSON issues with code
                    fixed_json = json_match.group()
                    # Replace unescaped newlines in strings
                    fixed_json = re.sub(r'("(?:[^"\\]|\\.)*?")', 
                                      lambda m: m.group(0).replace('\n', '\\n').replace('\r', '\\r'), 
                                      fixed_json)
                    try:
                        result = json.loads(fixed_json)
                        logger.warning("Fixed malformed JSON from Claude")
                    except json.JSONDecodeError:
                        raise ValueError(f"Failed to parse Claude response as JSON. Response: {response[:500]}...")
            else:
                raise ValueError(f"Failed to parse Claude response as JSON. Response: {response[:500]}...")
        
        # Get the recommended solution
        solutions = result.get("solutions", [])
        if not solutions:
            raise ValueError("No solutions provided")
        
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
            }
        )
        
        # If debugging an existing artifact, link the fixed version
        problematic_artifact_id = task.metadata.get("problematic_artifact_id")
        if problematic_artifact_id and context.artifact_manager:
            try:
                problematic_artifact = await context.artifact_manager.get_artifact(UUID(problematic_artifact_id))
                if problematic_artifact:
                    await self._link_artifacts(artifact, problematic_artifact, context)
            except Exception as e:
                logger.warning(f"Failed to link to problematic artifact: {e}")
        
        return [artifact]