"""Failure analysis and retry strategy system.

This module provides intelligent failure analysis and retry strategies
for the agentic coding system.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from uuid import UUID

from src.core.interfaces import Task, TaskContext
from src.utils.app_logging import get_logger

logger = get_logger(__name__)


class ErrorType(Enum):
    """Types of errors that can occur."""
    API_RATE_LIMIT = "api_rate_limit"
    API_TIMEOUT = "api_timeout"
    API_SERVER_ERROR = "api_server_error"
    CLI_MALFORMED_RESPONSE = "cli_malformed_response"
    CLI_COMMAND_FAILED = "cli_command_failed"
    COMPILATION_ERROR = "compilation_error"
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    TEST_FAILURE = "test_failure"
    VERIFICATION_TIMEOUT = "verification_timeout"
    DEPENDENCY_MISSING = "dependency_missing"
    TASK_TIMEOUT = "task_timeout"
    UNKNOWN = "unknown"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


class RetryStrategy(Enum):
    """Strategies for retrying failed tasks."""
    IMMEDIATE = "immediate"
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    MODIFY_PROMPT = "modify_prompt"
    SIMPLIFY_TASK = "simplify_task"
    INCREASE_TIMEOUT = "increase_timeout"
    WAIT_AND_RETRY = "wait_and_retry"
    SKIP = "skip"
    SPLIT_TASK = "split_task"


@dataclass
class ErrorDiagnosis:
    """Detailed diagnosis of an error."""
    error_type: ErrorType
    error_message: str
    is_retryable: bool
    retry_strategy: RetryStrategy
    suggested_fix: Optional[str] = None
    retry_delay: float = 2.0
    confidence: float = 0.8
    patterns_matched: List[str] = None
    context: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.patterns_matched is None:
            self.patterns_matched = []
        if self.context is None:
            self.context = {}


@dataclass
class TaskFailure:
    """Record of a task failure."""
    task_id: UUID
    task_name: str
    attempt: int
    timestamp: datetime
    error_type: ErrorType
    error_message: str
    diagnosis: ErrorDiagnosis
    cli_response: Optional[str] = None
    agent_id: Optional[UUID] = None


class FailureAnalyzer:
    """Analyzes failures and determines retry strategies."""
    
    def __init__(self):
        """Initialize the failure analyzer."""
        self.failure_history: Dict[UUID, List[TaskFailure]] = {}
        self.error_patterns = self._init_error_patterns()
        
    def _init_error_patterns(self) -> Dict[ErrorType, List[re.Pattern]]:
        """Initialize regex patterns for error detection."""
        return {
            ErrorType.API_RATE_LIMIT: [
                re.compile(r"rate.*limit", re.IGNORECASE),
                re.compile(r"429|too.*many.*requests", re.IGNORECASE),
                re.compile(r"quota.*exceeded", re.IGNORECASE),
            ],
            ErrorType.API_TIMEOUT: [
                re.compile(r"timeout|timed.*out", re.IGNORECASE),
                re.compile(r"deadline.*exceeded", re.IGNORECASE),
                re.compile(r"connection.*timeout", re.IGNORECASE),
            ],
            ErrorType.API_SERVER_ERROR: [
                re.compile(r"50[0-9]|server.*error", re.IGNORECASE),
                re.compile(r"internal.*server.*error", re.IGNORECASE),
                re.compile(r"service.*unavailable", re.IGNORECASE),
            ],
            ErrorType.CLI_MALFORMED_RESPONSE: [
                re.compile(r"failed.*parse.*json", re.IGNORECASE),
                re.compile(r"expecting.*value", re.IGNORECASE),
                re.compile(r"json.*decode.*error", re.IGNORECASE),
            ],
            ErrorType.COMPILATION_ERROR: [
                re.compile(r"syntax.*error", re.IGNORECASE),
                re.compile(r"compilation.*failed", re.IGNORECASE),
                re.compile(r"invalid.*syntax", re.IGNORECASE),
            ],
            ErrorType.IMPORT_ERROR: [
                re.compile(r"import.*error", re.IGNORECASE),
                re.compile(r"module.*not.*found", re.IGNORECASE),
                re.compile(r"no.*module.*named", re.IGNORECASE),
            ],
            ErrorType.TEST_FAILURE: [
                re.compile(r"test.*failed", re.IGNORECASE),
                re.compile(r"assertion.*error", re.IGNORECASE),
                re.compile(r"test.*error", re.IGNORECASE),
            ],
            ErrorType.DEPENDENCY_MISSING: [
                re.compile(r"dependency.*missing", re.IGNORECASE),
                re.compile(r"prerequisite.*failed", re.IGNORECASE),
                re.compile(r"blocked.*by", re.IGNORECASE),
            ],
        }
    
    async def analyze_error(
        self, 
        task: Task, 
        error: Exception, 
        context: Dict[str, Any]
    ) -> ErrorDiagnosis:
        """Analyze an error and determine root cause.
        
        Args:
            task: The failed task
            error: The exception that occurred
            context: Additional context (e.g., CLI response, attempt number)
            
        Returns:
            Detailed error diagnosis
        """
        error_str = str(error)
        error_type = ErrorType.UNKNOWN
        matched_patterns = []
        
        # Check for specific error patterns
        for err_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern.search(error_str):
                    error_type = err_type
                    matched_patterns.append(pattern.pattern)
                    break
            if error_type != ErrorType.UNKNOWN:
                break
        
        # Special handling for CLI response issues
        cli_response = context.get("cli_response", "")
        if cli_response and len(cli_response) == 15 and cli_response.isalnum():
            error_type = ErrorType.CLI_MALFORMED_RESPONSE
            matched_patterns.append("15-character CLI response")
        
        # Determine retry strategy
        retry_strategy = await self.get_retry_strategy(error_type, task, context)
        
        # Check if error is retryable
        is_retryable = self._is_error_retryable(error_type, context)
        
        # Generate suggested fix
        suggested_fix = await self._generate_fix_suggestion(
            error_type, task, error_str, context
        )
        
        # Calculate retry delay
        retry_delay = self._calculate_retry_delay(error_type, context)
        
        diagnosis = ErrorDiagnosis(
            error_type=error_type,
            error_message=error_str,
            is_retryable=is_retryable,
            retry_strategy=retry_strategy,
            suggested_fix=suggested_fix,
            retry_delay=retry_delay,
            patterns_matched=matched_patterns,
            context=context
        )
        
        # Record failure
        self._record_failure(task, diagnosis, context)
        
        logger.info(
            "Error analyzed",
            task_id=task.id,
            error_type=error_type.value,
            is_retryable=is_retryable,
            retry_strategy=retry_strategy.value
        )
        
        return diagnosis
    
    async def get_retry_strategy(
        self, 
        error_type: ErrorType,
        task: Task,
        context: Dict[str, Any]
    ) -> RetryStrategy:
        """Determine retry strategy based on error type.
        
        Args:
            error_type: Type of error
            task: The failed task
            context: Additional context
            
        Returns:
            Appropriate retry strategy
        """
        attempt = context.get("attempt", 1)
        
        # API errors - use exponential backoff
        if error_type in [ErrorType.API_RATE_LIMIT, ErrorType.API_TIMEOUT]:
            return RetryStrategy.EXPONENTIAL_BACKOFF
        
        # Server errors - wait and retry
        if error_type == ErrorType.API_SERVER_ERROR:
            return RetryStrategy.WAIT_AND_RETRY
        
        # CLI response issues - modify prompt
        if error_type == ErrorType.CLI_MALFORMED_RESPONSE:
            if attempt == 1:
                return RetryStrategy.MODIFY_PROMPT
            elif attempt == 2:
                return RetryStrategy.SIMPLIFY_TASK
            else:
                return RetryStrategy.SPLIT_TASK
        
        # Compilation errors - skip retry unless it's a simple fix
        if error_type in [ErrorType.COMPILATION_ERROR, ErrorType.SYNTAX_ERROR]:
            # Check if it's a simple syntax error that might be fixed
            if "missing colon" in context.get("error_message", "").lower():
                return RetryStrategy.MODIFY_PROMPT
            return RetryStrategy.SKIP
        
        # Import errors - usually permanent
        if error_type == ErrorType.IMPORT_ERROR:
            return RetryStrategy.SKIP
        
        # Test failures - might need timeout increase
        if error_type == ErrorType.TEST_FAILURE:
            if "timeout" in context.get("error_message", "").lower():
                return RetryStrategy.INCREASE_TIMEOUT
            return RetryStrategy.MODIFY_PROMPT
        
        # Dependency issues - wait for dependencies
        if error_type == ErrorType.DEPENDENCY_MISSING:
            return RetryStrategy.WAIT_AND_RETRY
        
        # Default strategy
        if attempt < 3:
            return RetryStrategy.EXPONENTIAL_BACKOFF
        else:
            return RetryStrategy.SKIP
    
    async def generate_fix_prompt(
        self, 
        task: Task, 
        diagnosis: ErrorDiagnosis
    ) -> str:
        """Generate improved prompt for retry attempt.
        
        Args:
            task: The failed task
            diagnosis: Error diagnosis
            
        Returns:
            Modified prompt for retry
        """
        original_prompt = task.description
        
        if diagnosis.retry_strategy == RetryStrategy.MODIFY_PROMPT:
            if diagnosis.error_type == ErrorType.CLI_MALFORMED_RESPONSE:
                # Add explicit JSON format request
                return f"""{original_prompt}

IMPORTANT: Return your response in the following JSON format:
{{
    "filename": "name_of_file.py",
    "code": "the actual code content",
    "description": "brief description of what was generated"
}}

Ensure the response is valid JSON that can be parsed."""
            
            elif diagnosis.error_type == ErrorType.TEST_FAILURE:
                # Add test-specific guidance
                return f"""{original_prompt}

Additional requirements:
- Ensure all imports are at the top of the file
- Add proper error handling for edge cases
- Include type hints for all functions
- Make sure all test assertions have descriptive messages"""
            
            else:
                # Generic improvement
                return f"""{original_prompt}

Previous attempt failed with: {diagnosis.error_message}
Please ensure the code is complete, properly formatted, and handles edge cases."""
        
        elif diagnosis.retry_strategy == RetryStrategy.SIMPLIFY_TASK:
            # Simplify the task
            lines = original_prompt.strip().split('\n')
            if len(lines) > 5:
                # Take only the core requirements
                core_lines = [line for line in lines if any(
                    keyword in line.lower() 
                    for keyword in ['create', 'implement', 'build', 'write']
                )][:3]
                return '\n'.join(core_lines) + "\n\nFocus on the core functionality only."
            return original_prompt
        
        elif diagnosis.retry_strategy == RetryStrategy.SPLIT_TASK:
            # Suggest splitting into subtasks
            return f"""The following task is complex. Please implement ONLY the first part:

{original_prompt}

Start with the basic structure and core functionality only."""
        
        return original_prompt
    
    def _is_error_retryable(self, error_type: ErrorType, context: Dict[str, Any]) -> bool:
        """Determine if an error is retryable.
        
        Args:
            error_type: Type of error
            context: Additional context
            
        Returns:
            True if error is retryable
        """
        # Permanent errors
        permanent_errors = {
            ErrorType.IMPORT_ERROR,
            ErrorType.COMPILATION_ERROR,
            ErrorType.SYNTAX_ERROR,
        }
        
        # Check attempt count
        attempt = context.get("attempt", 1)
        max_attempts = context.get("max_attempts", 3)
        
        if attempt >= max_attempts:
            return False
        
        # Some errors are permanent
        if error_type in permanent_errors:
            # Unless we have a specific fix strategy
            if error_type == ErrorType.COMPILATION_ERROR:
                error_msg = context.get("error_message", "").lower()
                if any(fixable in error_msg for fixable in ["missing colon", "indentation"]):
                    return True
            return False
        
        # Transient errors are always retryable
        transient_errors = {
            ErrorType.API_RATE_LIMIT,
            ErrorType.API_TIMEOUT,
            ErrorType.API_SERVER_ERROR,
            ErrorType.CLI_MALFORMED_RESPONSE,
            ErrorType.VERIFICATION_TIMEOUT,
            ErrorType.TRANSIENT,
        }
        
        return error_type in transient_errors or error_type == ErrorType.UNKNOWN
    
    def _calculate_retry_delay(self, error_type: ErrorType, context: Dict[str, Any]) -> float:
        """Calculate delay before retry.
        
        Args:
            error_type: Type of error
            context: Additional context
            
        Returns:
            Delay in seconds
        """
        base_delay = context.get("base_delay", 2.0)
        attempt = context.get("attempt", 1)
        backoff_multiplier = context.get("backoff_multiplier", 2.0)
        
        if error_type == ErrorType.API_RATE_LIMIT:
            # Check if we have rate limit info
            if "retry_after" in context:
                return float(context["retry_after"])
            # Otherwise use exponential backoff
            return min(base_delay * (backoff_multiplier ** (attempt - 1)), 60.0)
        
        elif error_type in [ErrorType.API_TIMEOUT, ErrorType.API_SERVER_ERROR]:
            # Exponential backoff with cap
            return min(base_delay * (backoff_multiplier ** (attempt - 1)), 30.0)
        
        elif error_type == ErrorType.DEPENDENCY_MISSING:
            # Wait longer for dependencies
            return base_delay * 3
        
        else:
            # Standard delay
            return base_delay
    
    async def _generate_fix_suggestion(
        self,
        error_type: ErrorType,
        task: Task,
        error_message: str,
        context: Dict[str, Any]
    ) -> Optional[str]:
        """Generate a suggestion for fixing the error.
        
        Args:
            error_type: Type of error
            task: The failed task
            error_message: Error message
            context: Additional context
            
        Returns:
            Suggestion for fixing the error
        """
        suggestions = {
            ErrorType.CLI_MALFORMED_RESPONSE: 
                "Claude CLI returned malformed response. Consider using API directly or simplifying the prompt.",
            ErrorType.API_RATE_LIMIT:
                "Hit API rate limit. Wait before retrying or reduce request frequency.",
            ErrorType.IMPORT_ERROR:
                f"Missing import in generated code. Ensure all dependencies are specified in the task.",
            ErrorType.TEST_FAILURE:
                "Tests failed. Review test implementation and ensure proper mocking/fixtures.",
            ErrorType.COMPILATION_ERROR:
                "Code has syntax errors. Review generated code for completeness.",
            ErrorType.DEPENDENCY_MISSING:
                "Task depends on incomplete prerequisites. Complete dependencies first.",
        }
        
        return suggestions.get(error_type, f"Error: {error_message[:100]}")
    
    def _record_failure(
        self, 
        task: Task, 
        diagnosis: ErrorDiagnosis,
        context: Dict[str, Any]
    ) -> None:
        """Record a task failure for history tracking.
        
        Args:
            task: The failed task
            diagnosis: Error diagnosis
            context: Additional context
        """
        failure = TaskFailure(
            task_id=task.id,
            task_name=task.name,
            attempt=context.get("attempt", 1),
            timestamp=datetime.utcnow(),
            error_type=diagnosis.error_type,
            error_message=diagnosis.error_message,
            diagnosis=diagnosis,
            cli_response=context.get("cli_response"),
            agent_id=context.get("agent_id")
        )
        
        if task.id not in self.failure_history:
            self.failure_history[task.id] = []
        
        self.failure_history[task.id].append(failure)
    
    def get_task_failure_history(self, task_id: UUID) -> List[TaskFailure]:
        """Get failure history for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of task failures
        """
        return self.failure_history.get(task_id, [])