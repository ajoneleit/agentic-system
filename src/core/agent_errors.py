"""Comprehensive error hierarchy for agent Result[T] pattern.

This module defines specific error types for each agent type to enable
precise error handling with the Result[T] monad pattern.
"""

from typing import Any, Dict, Optional, List
from uuid import UUID


class AgentResultError(Exception):
    """Base error type for all agent Result[T] errors."""
    
    def __init__(
        self,
        message: str,
        agent_id: Optional[UUID] = None,
        task_id: Optional[UUID] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        """Initialize agent error.
        
        Args:
            message: Human-readable error message
            agent_id: ID of the agent that encountered the error
            task_id: ID of the task being executed
            details: Additional error context
        """
        super().__init__(message)
        self.message = message
        self.agent_id = agent_id
        self.task_id = task_id
        self.details = details or {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "agent_id": str(self.agent_id) if self.agent_id else None,
            "task_id": str(self.task_id) if self.task_id else None,
            "details": self.details
        }


# Meta Agent Errors
class MetaAgentError(AgentResultError):
    """Errors specific to Meta Agent orchestration."""
    pass


class TaskDecompositionError(MetaAgentError):
    """Error during task decomposition."""
    pass


class AgentSpawnError(MetaAgentError):
    """Error spawning sub-agents."""
    pass


class OrchestrationError(MetaAgentError):
    """Error during task orchestration."""
    pass


class ResultAggregationError(MetaAgentError):
    """Error aggregating results from sub-agents."""
    pass


# Code Generation Errors
class CodeGenerationError(AgentResultError):
    """Errors specific to code generation agents."""
    pass


class SyntaxValidationError(CodeGenerationError):
    """Error validating generated code syntax."""
    pass


class CodeComplexityError(CodeGenerationError):
    """Generated code exceeds complexity limits."""
    pass


# Test Generation Errors
class TestGenerationError(AgentResultError):
    """Errors specific to test generation agents."""
    pass


class TestCoverageError(TestGenerationError):
    """Test coverage requirements not met."""
    pass


class TestExecutionError(TestGenerationError):
    """Error executing generated tests."""
    pass


# Debug Agent Errors
class DebugError(AgentResultError):
    """Errors specific to debug agents."""
    pass


class DiagnosisError(DebugError):
    """Error diagnosing code issues."""
    pass


class FixApplicationError(DebugError):
    """Error applying suggested fixes."""
    pass


# Refactor Agent Errors
class RefactorError(AgentResultError):
    """Errors specific to refactoring agents."""
    pass


class CodeAnalysisError(RefactorError):
    """Error analyzing code for refactoring."""
    pass


class RefactoringValidationError(RefactorError):
    """Refactored code failed validation."""
    pass


# Documentation Agent Errors
class DocGenerationError(AgentResultError):
    """Errors specific to documentation agents."""
    pass


class DocFormatError(DocGenerationError):
    """Documentation format validation error."""
    pass


class DocCompletenessError(DocGenerationError):
    """Documentation missing required sections."""
    pass


# Common Validation Errors
class ValidationError(AgentResultError):
    """General validation errors."""
    pass


class InputValidationError(ValidationError):
    """Invalid input parameters."""
    pass


class OutputValidationError(ValidationError):
    """Generated output failed validation."""
    pass


class DependencyError(ValidationError):
    """Task dependencies not satisfied."""
    pass


# CLI-specific Errors
class CLIError(AgentResultError):
    """Errors related to Claude Code operations."""
    pass


class CLINotAvailableError(CLIError):
    """Claude Code is not available."""
    pass


class CLITimeoutError(CLIError):
    """Claude Code operation timed out."""
    pass


class CLIResponseError(CLIError):
    """Invalid response from Claude Code."""
    pass


# Workspace Errors
class WorkspaceError(AgentResultError):
    """Errors related to workspace operations."""
    pass


class FileNotFoundError(WorkspaceError):
    """Required file not found in workspace."""
    pass


class FileAccessError(WorkspaceError):
    """Cannot access file in workspace."""
    pass


class WorkspaceIndexError(WorkspaceError):
    """Error indexing workspace files."""
    pass


# Resource Management Errors
class ResourceExhaustionError(AgentResultError):
    """Resource exhaustion error (memory, disk, CPU)."""
    pass


# Aggregate Error for multiple failures
class AggregateError(AgentResultError):
    """Container for multiple errors."""
    
    def __init__(self, errors: List[Exception], message: Optional[str] = None):
        """Initialize aggregate error.
        
        Args:
            errors: List of errors that occurred
            message: Optional summary message
        """
        if not message:
            message = f"Multiple errors occurred: {len(errors)} failures"
        
        super().__init__(message)
        self.errors = errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary including all sub-errors."""
        base_dict = super().to_dict()
        base_dict["errors"] = [
            e.to_dict() if hasattr(e, "to_dict") else str(e)
            for e in self.errors
        ]
        return base_dict