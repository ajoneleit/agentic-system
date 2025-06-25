"""Custom exception hierarchy for the Agentic Coding System.

This module defines specific exceptions for different failure modes,
enabling precise error handling and recovery strategies throughout the system.
"""

from typing import Any, Dict, Optional
from uuid import UUID


class AgenticSystemError(Exception):
    """Base exception for all Agentic System errors.
    
    All custom exceptions in the system inherit from this base class,
    enabling consistent error handling and logging.
    """
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize base exception.
        
        Args:
            message: Human-readable error message
            error_code: Machine-readable error code for programmatic handling
            details: Additional error context and debugging information
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization.
        
        Returns:
            Dictionary representation of the exception
        """
        return {
            "error_type": self.__class__.__name__,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
        }


# Task-related exceptions
class TaskError(AgenticSystemError):
    """Base exception for task-related errors."""
    
    def __init__(self, task_id: UUID, message: str, **kwargs: Any):
        """Initialize task error with task ID.
        
        Args:
            task_id: ID of the task that caused the error
            message: Error message
            **kwargs: Additional error details
        """
        super().__init__(message, details={"task_id": str(task_id), **kwargs})
        self.task_id = task_id


class TaskDecompositionError(TaskError):
    """Raised when task decomposition fails."""
    
    def __init__(self, task_id: UUID, user_prompt: str, reason: str):
        """Initialize task decomposition error.
        
        Args:
            task_id: ID of the parent task
            user_prompt: Original user prompt that failed decomposition
            reason: Reason for decomposition failure
        """
        super().__init__(
            task_id,
            f"Failed to decompose task: {reason}",
            user_prompt=user_prompt,
            reason=reason,
        )
        self.user_prompt = user_prompt
        self.reason = reason


class TaskDependencyError(TaskError):
    """Raised when task dependencies cannot be resolved."""
    
    def __init__(self, task_id: UUID, missing_deps: list[UUID]):
        """Initialize dependency error.
        
        Args:
            task_id: ID of the task with missing dependencies
            missing_deps: List of missing dependency IDs
        """
        super().__init__(
            task_id,
            f"Task has {len(missing_deps)} unresolved dependencies",
            missing_dependencies=[str(dep) for dep in missing_deps],
        )


class TaskExecutionError(TaskError):
    """Raised when task execution fails."""
    
    def __init__(self, task_id: UUID, agent_id: UUID, reason: str):
        """Initialize execution error.
        
        Args:
            task_id: ID of the failed task
            agent_id: ID of the agent that failed
            reason: Reason for execution failure
        """
        super().__init__(
            task_id,
            f"Task execution failed: {reason}",
            agent_id=str(agent_id),
            reason=reason,
        )
        self.agent_id = agent_id


# Agent-related exceptions
class AgentError(AgenticSystemError):
    """Base exception for agent-related errors."""
    
    def __init__(self, agent_id: UUID, message: str, **kwargs: Any):
        """Initialize agent error.
        
        Args:
            agent_id: ID of the agent that caused the error
            message: Error message
            **kwargs: Additional error details
        """
        super().__init__(message, details={"agent_id": str(agent_id), **kwargs})
        self.agent_id = agent_id


class AgentInitializationError(AgentError):
    """Raised when agent initialization fails."""
    
    def __init__(self, agent_id: UUID, role: str, reason: str):
        """Initialize agent initialization error.
        
        Args:
            agent_id: ID of the agent
            role: Role the agent was supposed to fulfill
            reason: Reason for initialization failure
        """
        super().__init__(
            agent_id,
            f"Failed to initialize {role} agent: {reason}",
            role=role,
            reason=reason,
        )


class AgentCommunicationError(AgentError):
    """Raised when inter-agent communication fails."""
    
    def __init__(
        self,
        sender_id: UUID,
        receiver_id: UUID,
        message_type: str,
        reason: str,
    ):
        """Initialize communication error.
        
        Args:
            sender_id: ID of the sending agent
            receiver_id: ID of the receiving agent
            message_type: Type of message that failed
            reason: Reason for communication failure
        """
        super().__init__(
            sender_id,
            f"Communication failed between agents: {reason}",
            receiver_id=str(receiver_id),
            message_type=message_type,
            reason=reason,
        )


class AgentOverloadError(AgentError):
    """Raised when an agent is overloaded with tasks."""
    
    def __init__(self, agent_id: UUID, current_tasks: int, max_tasks: int):
        """Initialize overload error.
        
        Args:
            agent_id: ID of the overloaded agent
            current_tasks: Number of current tasks
            max_tasks: Maximum allowed tasks
        """
        super().__init__(
            agent_id,
            f"Agent overloaded: {current_tasks} tasks (max: {max_tasks})",
            current_tasks=current_tasks,
            max_tasks=max_tasks,
        )


# API-related exceptions
class APIError(AgenticSystemError):
    """Base exception for API-related errors."""
    
    pass


class APIKeyError(APIError):
    """Raised when API key is invalid or missing."""
    
    def __init__(self, service: str = "Anthropic"):
        """Initialize API key error.
        
        Args:
            service: Name of the API service
        """
        super().__init__(
            f"{service} API key is invalid or missing",
            error_code="INVALID_API_KEY",
            details={"service": service},
        )


class APIRateLimitError(APIError):
    """Raised when API rate limit is exceeded."""
    
    def __init__(
        self,
        retry_after: Optional[int] = None,
        limit_type: str = "requests",
    ):
        """Initialize rate limit error.
        
        Args:
            retry_after: Seconds to wait before retrying
            limit_type: Type of limit exceeded (requests, tokens, etc.)
        """
        super().__init__(
            f"API rate limit exceeded for {limit_type}",
            error_code="RATE_LIMIT_EXCEEDED",
            details={
                "retry_after_seconds": retry_after,
                "limit_type": limit_type,
            },
        )
        self.retry_after = retry_after


class APIResponseError(APIError):
    """Raised when API returns an unexpected response."""
    
    def __init__(
        self,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None,
        reason: str = "Unexpected API response",
    ):
        """Initialize API response error.
        
        Args:
            status_code: HTTP status code
            response_body: Response body for debugging
            reason: Human-readable reason
        """
        super().__init__(
            reason,
            error_code="API_RESPONSE_ERROR",
            details={
                "status_code": status_code,
                "response_body": response_body[:500] if response_body else None,
            },
        )


class APITimeoutError(APIError):
    """Raised when API request times out."""
    
    def __init__(self, timeout_seconds: int, operation: str):
        """Initialize timeout error.
        
        Args:
            timeout_seconds: Timeout duration
            operation: Operation that timed out
        """
        super().__init__(
            f"API request timed out after {timeout_seconds}s during {operation}",
            error_code="API_TIMEOUT",
            details={
                "timeout_seconds": timeout_seconds,
                "operation": operation,
            },
        )


# Verification-related exceptions
class VerificationError(AgenticSystemError):
    """Base exception for verification-related errors."""
    
    def __init__(
        self,
        artifact_id: UUID,
        verification_type: str,
        message: str,
        **kwargs: Any,
    ):
        """Initialize verification error.
        
        Args:
            artifact_id: ID of the artifact that failed verification
            verification_type: Type of verification that failed
            message: Error message
            **kwargs: Additional error details
        """
        super().__init__(
            message,
            details={
                "artifact_id": str(artifact_id),
                "verification_type": verification_type,
                **kwargs,
            },
        )
        self.artifact_id = artifact_id
        self.verification_type = verification_type


class CompilationError(VerificationError):
    """Raised when code compilation fails."""
    
    def __init__(
        self,
        artifact_id: UUID,
        errors: list[str],
        warnings: list[str],
        language: str,
    ):
        """Initialize compilation error.
        
        Args:
            artifact_id: ID of the artifact
            errors: List of compilation errors
            warnings: List of compilation warnings
            language: Programming language
        """
        super().__init__(
            artifact_id,
            "compilation",
            f"Compilation failed with {len(errors)} errors",
            errors=errors,
            warnings=warnings,
            language=language,
        )


class TestFailureError(VerificationError):
    """Raised when tests fail."""
    
    def __init__(
        self,
        artifact_id: UUID,
        failed_tests: list[str],
        passed_tests: int,
        total_tests: int,
        coverage: Optional[float] = None,
    ):
        """Initialize test failure error.
        
        Args:
            artifact_id: ID of the artifact
            failed_tests: List of failed test names
            passed_tests: Number of passed tests
            total_tests: Total number of tests
            coverage: Code coverage percentage
        """
        super().__init__(
            artifact_id,
            "testing",
            f"{len(failed_tests)} of {total_tests} tests failed",
            failed_tests=failed_tests,
            passed_tests=passed_tests,
            total_tests=total_tests,
            coverage=coverage,
        )


class QualityCheckError(VerificationError):
    """Raised when code quality checks fail."""
    
    def __init__(
        self,
        artifact_id: UUID,
        quality_issues: dict[str, list[str]],
        quality_score: float,
    ):
        """Initialize quality check error.
        
        Args:
            artifact_id: ID of the artifact
            quality_issues: Dictionary of quality issue categories and issues
            quality_score: Overall quality score
        """
        super().__init__(
            artifact_id,
            "quality",
            f"Quality check failed with score {quality_score:.2f}",
            quality_issues=quality_issues,
            quality_score=quality_score,
        )


# Artifact-related exceptions
class ArtifactError(AgenticSystemError):
    """Base exception for artifact-related errors."""
    
    pass


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact cannot be found."""
    
    def __init__(self, artifact_id: UUID):
        """Initialize not found error.
        
        Args:
            artifact_id: ID of the missing artifact
        """
        super().__init__(
            f"Artifact {artifact_id} not found",
            error_code="ARTIFACT_NOT_FOUND",
            details={"artifact_id": str(artifact_id)},
        )


class ArtifactVersionConflictError(ArtifactError):
    """Raised when artifact version conflicts occur."""
    
    def __init__(
        self,
        artifact_name: str,
        current_version: int,
        requested_version: int,
    ):
        """Initialize version conflict error.
        
        Args:
            artifact_name: Name of the artifact
            current_version: Current version number
            requested_version: Requested version number
        """
        super().__init__(
            f"Version conflict for {artifact_name}: current={current_version}, requested={requested_version}",
            error_code="VERSION_CONFLICT",
            details={
                "artifact_name": artifact_name,
                "current_version": current_version,
                "requested_version": requested_version,
            },
        )


class ArtifactDependencyError(ArtifactError):
    """Raised when artifact dependencies cannot be resolved."""
    
    def __init__(
        self,
        artifact_id: UUID,
        missing_dependencies: list[UUID],
    ):
        """Initialize dependency error.
        
        Args:
            artifact_id: ID of the artifact
            missing_dependencies: List of missing dependency IDs
        """
        super().__init__(
            f"Cannot resolve dependencies for artifact {artifact_id}",
            error_code="DEPENDENCY_ERROR",
            details={
                "artifact_id": str(artifact_id),
                "missing_dependencies": [str(dep) for dep in missing_dependencies],
            },
        )


# Configuration-related exceptions
class ConfigurationError(AgenticSystemError):
    """Base exception for configuration errors."""
    
    pass


class InvalidConfigurationError(ConfigurationError):
    """Raised when configuration is invalid."""
    
    def __init__(self, config_key: str, reason: str, suggestion: Optional[str] = None):
        """Initialize invalid configuration error.
        
        Args:
            config_key: Configuration key that is invalid
            reason: Reason why configuration is invalid
            suggestion: Suggested fix
        """
        details = {
            "config_key": config_key,
            "reason": reason,
        }
        if suggestion:
            details["suggestion"] = suggestion
            
        super().__init__(
            f"Invalid configuration for '{config_key}': {reason}",
            error_code="INVALID_CONFIG",
            details=details,
        )


class MissingConfigurationError(ConfigurationError):
    """Raised when required configuration is missing."""
    
    def __init__(self, config_key: str, env_var: Optional[str] = None):
        """Initialize missing configuration error.
        
        Args:
            config_key: Missing configuration key
            env_var: Environment variable name if applicable
        """
        message = f"Required configuration '{config_key}' is missing"
        details = {"config_key": config_key}
        
        if env_var:
            message += f" (environment variable: {env_var})"
            details["env_var"] = env_var
            
        super().__init__(
            message,
            error_code="MISSING_CONFIG",
            details=details,
        )