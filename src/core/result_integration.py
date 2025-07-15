"""Integration utilities for Result[T] pattern throughout the system.

This module provides decorators, converters, and patterns for integrating
the Result[T] monad with existing agent code.
"""

import asyncio
import functools
from typing import Any, Callable, TypeVar, Union, overload

from src.core.result import (
    Result,
    AsyncResult,
    collect_results,
    collect_async_results,
    result_handler,
    async_result_handler,
)
from src.core.exceptions import AgenticSystemError
from src.utils.app_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


# Conversion utilities for backward compatibility
def exception_to_result(func: Callable[..., T]) -> Callable[..., Result[T]]:
    """Convert exception-raising functions to Result-returning functions.
    
    This decorator catches exceptions and converts them to Result.failure().
    Use this for gradual migration of existing code.
    
    Example:
        @exception_to_result
        def risky_operation(x: int) -> int:
            if x < 0:
                raise ValueError("x must be non-negative")
            return x * 2
            
        result = risky_operation(-1)  # Returns Result.failure(ValueError(...))
    """
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
        try:
            return Result.success(func(*args, **kwargs))
        except Exception as e:
            logger.debug(
                f"Converted exception to Result.failure in {func.__name__}",
                error=str(e)
            )
            return Result.failure(e)
    return wrapper


def async_exception_to_result(
    func: Callable[..., asyncio.Awaitable[T]]
) -> Callable[..., asyncio.Awaitable[Result[T]]]:
    """Convert async exception-raising functions to Result-returning functions.
    
    This decorator catches exceptions in async functions and converts them to Result.failure().
    
    Example:
        @async_exception_to_result
        async def async_risky_operation(x: int) -> int:
            if x < 0:
                raise ValueError("x must be non-negative")
            await asyncio.sleep(0.1)
            return x * 2
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
        try:
            return Result.success(await func(*args, **kwargs))
        except Exception as e:
            logger.debug(
                f"Converted exception to Result.failure in async {func.__name__}",
                error=str(e)
            )
            return Result.failure(e)
    return wrapper


# Result chain builders for complex operations
class ResultChain:
    """Build chains of Result operations with error handling.
    
    Example:
        result = (
            ResultChain(get_user(user_id))
            .then(lambda user: validate_permissions(user))
            .then(lambda _: load_project(project_id))
            .then(lambda project: generate_code(project))
            .unwrap_or_else(lambda e: handle_error(e))
        )
    """
    
    def __init__(self, initial: Result[T]):
        """Initialize chain with a Result."""
        self._result = initial
    
    def then(self, func: Callable[[T], Result[Any]]) -> 'ResultChain':
        """Chain another operation."""
        self._result = self._result.flat_map(func)
        return self
    
    def map(self, func: Callable[[T], Any]) -> 'ResultChain':
        """Map the value if successful."""
        self._result = self._result.map(func)
        return self
    
    def recover(self, func: Callable[[Exception], Result[T]]) -> 'ResultChain':
        """Recover from errors."""
        self._result = self._result.or_else(func)
        return self
    
    def get(self) -> Result[T]:
        """Get the final Result."""
        return self._result
    
    def unwrap_or_else(self, func: Callable[[Exception], T]) -> T:
        """Unwrap or provide default."""
        return self._result.unwrap_or_else(func)


# Async Result chain builder
class AsyncResultChain:
    """Build chains of async Result operations.
    
    Example:
        result = await (
            AsyncResultChain(fetch_user(user_id))
            .then(lambda user: validate_permissions_async(user))
            .then(lambda _: load_project_async(project_id))
            .then(lambda project: generate_code_async(project))
            .get()
        )
    """
    
    def __init__(self, initial: Union[AsyncResult[T], asyncio.Awaitable[Result[T]]]):
        """Initialize with async Result."""
        if isinstance(initial, AsyncResult):
            self._async_result = initial
        else:
            self._async_result = AsyncResult(initial)
    
    def then(
        self,
        func: Callable[[T], asyncio.Awaitable[Result[Any]]]
    ) -> 'AsyncResultChain':
        """Chain async operation."""
        self._async_result = self._async_result.flat_map(func)
        return self
    
    def map(self, func: Callable[[T], Any]) -> 'AsyncResultChain':
        """Map the value if successful."""
        self._async_result = self._async_result.map(func)
        return self
    
    async def get(self) -> Result[T]:
        """Get the final Result."""
        return await self._async_result.get()


# Parallel operation utilities
async def execute_parallel_with_results(
    operations: list[Callable[[], asyncio.Awaitable[Result[T]]]]
) -> Result[list[T]]:
    """Execute operations in parallel and collect results.
    
    Args:
        operations: List of async functions returning Result[T]
        
    Returns:
        Result[list[T]] with all values or first error
        
    Example:
        operations = [
            lambda: fetch_data(url1),
            lambda: fetch_data(url2),
            lambda: fetch_data(url3),
        ]
        result = await execute_parallel_with_results(operations)
    """
    tasks = [asyncio.create_task(op()) for op in operations]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert any exceptions to Result.failure
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            processed_results.append(Result.failure(r))
        else:
            processed_results.append(r)
    
    return collect_results(processed_results)


# Error logging and telemetry
def log_result_errors(
    component: str,
    operation: str
) -> Callable[[Result[T]], Result[T]]:
    """Log errors from Result operations for monitoring.
    
    Args:
        component: Component name (e.g., "MetaAgent")
        operation: Operation name (e.g., "task_decomposition")
        
    Returns:
        Function that logs errors and returns the Result unchanged
        
    Example:
        result = (
            some_operation()
            .map(process_data)
            .map(log_result_errors("DataProcessor", "processing"))
            .flat_map(save_data)
        )
    """
    def log_errors(result: Result[T]) -> Result[T]:
        if result.is_failure():
            error = result.get_error()
            traceback = result.get_traceback()
            
            logger.error(
                "Operation failed",
                component=component,
                operation=operation,
                error_type=type(error).__name__,
                error_message=str(error),
                traceback=traceback,
            )
        return result
    
    return log_errors


# Validation utilities
def validate_result(
    validator: Callable[[T], bool],
    error_message: str
) -> Callable[[Result[T]], Result[T]]:
    """Validate Result value and convert to failure if invalid.
    
    Args:
        validator: Function to validate the value
        error_message: Error message if validation fails
        
    Returns:
        Function that validates and returns Result
        
    Example:
        result = (
            get_number()
            .map(lambda x: x * 2)
            .flat_map(validate_result(lambda x: x > 0, "Number must be positive"))
        )
    """
    def validate(result: Result[T]) -> Result[T]:
        if result.is_success():
            value = result.unwrap()
            if not validator(value):
                return Result.failure(
                    ValueError(f"{error_message}: {value}")
                )
        return result
    
    return validate


# Retry utilities for Result operations
async def retry_with_result(
    operation: Callable[[], asyncio.Awaitable[Result[T]]],
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    retry_on: tuple[type[Exception], ...] = (Exception,)
) -> Result[T]:
    """Retry an operation that returns Result[T].
    
    Args:
        operation: Async function returning Result[T]
        max_attempts: Maximum retry attempts
        delay: Initial delay between retries
        backoff_factor: Multiplier for delay after each retry
        retry_on: Tuple of exception types to retry on
        
    Returns:
        Result[T] from successful operation or last failure
    """
    current_delay = delay
    last_error = None
    
    for attempt in range(max_attempts):
        result = await operation()
        
        if result.is_success():
            return result
        
        error = result.get_error()
        if error and isinstance(error, retry_on) and attempt < max_attempts - 1:
            logger.warning(
                f"Operation failed on attempt {attempt + 1}/{max_attempts}, retrying...",
                error=str(error),
                retry_delay=current_delay
            )
            await asyncio.sleep(current_delay)
            current_delay *= backoff_factor
            last_error = error
        else:
            return result
    
    # Should not reach here, but for safety
    return Result.failure(
        last_error or RuntimeError(f"Failed after {max_attempts} attempts")
    )


# Circuit breaker pattern for Result operations
class CircuitBreaker:
    """Circuit breaker for Result-returning operations.
    
    Prevents repeated calls to failing operations.
    
    Example:
        breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
        
        @breaker.protect
        async def risky_operation() -> Result[str]:
            return await external_api_call()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: type[Exception] = Exception
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Failures before opening circuit
            recovery_timeout: Seconds before attempting recovery
            expected_exception: Exception type to count as failure
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = "closed"  # closed, open, half-open
    
    def protect(
        self,
        func: Callable[..., asyncio.Awaitable[Result[T]]]
    ) -> Callable[..., asyncio.Awaitable[Result[T]]]:
        """Protect an async function with circuit breaker."""
        
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
            if self.state == "open":
                if asyncio.get_event_loop().time() - self.last_failure_time > self.recovery_timeout:
                    self.state = "half-open"
                else:
                    return Result.failure(
                        RuntimeError("Circuit breaker is open")
                    )
            
            try:
                result = await func(*args, **kwargs)
                
                if result.is_failure():
                    error = result.get_error()
                    if isinstance(error, self.expected_exception):
                        self._record_failure()
                else:
                    self._record_success()
                
                return result
            except Exception as e:
                self._record_failure()
                return Result.failure(e)
        
        return wrapper
    
    def _record_success(self):
        """Record successful operation."""
        self.failure_count = 0
        self.state = "closed"
    
    def _record_failure(self):
        """Record failed operation."""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures"
            )