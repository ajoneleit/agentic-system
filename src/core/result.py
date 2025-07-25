"""Result[T] monad implementation for robust error handling.

This module provides a type-safe Result[T] type (similar to Rust's Result or Haskell's Either)
for handling errors without exceptions throughout the system. Every agent operation should
return a Result[T] instead of raising exceptions.

Key features:
- Type-safe error propagation
- Functional composition with map/flat_map
- Async support
- Error aggregation for parallel operations
"""

from __future__ import annotations

import asyncio
import functools
import traceback
from collections.abc import Awaitable
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Generic,
    TypeVar,
    cast,
    overload,
)

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E", bound=Exception)


@dataclass(frozen=True)
class Ok(Generic[T]):
    """Represents a successful result."""

    value: T


@dataclass(frozen=True)
class Err(Generic[E]):
    """Represents a failed result."""

    error: E
    traceback_str: str | None = None


class Result(Generic[T]):
    """Result[T] monad for error handling.

    A Result is either Ok(value) or Err(error), providing a type-safe way
    to handle errors without exceptions.

    Examples:
        >>> result = Result.success(42)
        >>> if result.is_success():
        ...     print(result.unwrap())
        42

        >>> result = Result.failure(ValueError("Invalid input"))
        >>> result.unwrap_or(0)
        0

    """

    def __init__(self, inner: Ok[T] | Err[Exception]):
        """Initialize Result with Ok or Err.

        Args:
            inner: Either Ok(value) or Err(error)

        """
        self._inner = inner

    @classmethod
    def success(cls, value: T) -> Result[T]:
        """Create a successful result.

        Args:
            value: The success value

        Returns:
            Result containing the value

        """
        return cls(Ok(value))

    @classmethod
    def failure(cls, error: Exception, capture_traceback: bool = True) -> Result[T]:
        """Create a failed result.

        Args:
            error: The error/exception
            capture_traceback: Whether to capture current stack trace

        Returns:
            Result containing the error

        """
        tb_str = None
        if capture_traceback:
            tb_str = traceback.format_exc()
        return cls(Err(error, tb_str))

    def is_success(self) -> bool:
        """Check if result is successful."""
        return isinstance(self._inner, Ok)

    def is_failure(self) -> bool:
        """Check if result is a failure."""
        return isinstance(self._inner, Err)

    def unwrap(self) -> T:
        """Get the value, raising if it's an error.

        Returns:
            The success value

        Raises:
            The contained error if result is Err

        """
        if isinstance(self._inner, Ok):
            return self._inner.value
        else:
            raise self._inner.error

    def unwrap_or(self, default: T) -> T:
        """Get the value or return default if error.

        Args:
            default: Value to return if result is error

        Returns:
            The success value or default

        """
        if isinstance(self._inner, Ok):
            return self._inner.value
        return default

    def unwrap_or_else(self, func: Callable[[Exception], T]) -> T:
        """Get the value or compute default from error.

        Args:
            func: Function to compute default from error

        Returns:
            The success value or computed default

        """
        if isinstance(self._inner, Ok):
            return self._inner.value
        return func(self._inner.error)

    def expect(self, message: str) -> T:
        """Get the value with custom error message.

        Args:
            message: Custom error message

        Returns:
            The success value

        Raises:
            RuntimeError with custom message if result is Err

        """
        if isinstance(self._inner, Ok):
            return self._inner.value
        raise RuntimeError(f"{message}: {self._inner.error}")

    def map(self, func: Callable[[T], U]) -> Result[U]:
        """Transform the success value.

        Args:
            func: Function to transform the value

        Returns:
            New Result with transformed value or same error

        """
        if isinstance(self._inner, Ok):
            try:
                return Result.success(func(self._inner.value))
            except Exception as e:
                return Result.failure(e)
        return cast(Result[U], self)

    def map_err(self, func: Callable[[Exception], Exception]) -> Result[T]:
        """Transform the error.

        Args:
            func: Function to transform the error

        Returns:
            Same success or Result with transformed error

        """
        if isinstance(self._inner, Err):
            try:
                return Result.failure(func(self._inner.error))
            except Exception as e:
                return Result.failure(e)
        return self

    def flat_map(self, func: Callable[[T], Result[U]]) -> Result[U]:
        """Chain operations that return Results.

        Args:
            func: Function returning a Result

        Returns:
            Result from func or propagated error

        """
        if isinstance(self._inner, Ok):
            try:
                return func(self._inner.value)
            except Exception as e:
                return Result.failure(e)
        return cast(Result[U], self)

    def and_then(self, func: Callable[[T], Result[U]]) -> Result[U]:
        """Alias for flat_map for better readability."""
        return self.flat_map(func)

    def or_else(self, func: Callable[[Exception], Result[T]]) -> Result[T]:
        """Try alternative on error.

        Args:
            func: Function to compute alternative Result

        Returns:
            Original success or alternative Result

        """
        if isinstance(self._inner, Err):
            try:
                return func(self._inner.error)
            except Exception as e:
                return Result.failure(e)
        return self

    def get_error(self) -> Exception | None:
        """Get the error if result is failure."""
        if isinstance(self._inner, Err):
            return self._inner.error
        return None

    def get_traceback(self) -> str | None:
        """Get the captured traceback if available."""
        if isinstance(self._inner, Err):
            return self._inner.traceback_str
        return None

    @overload
    def match(self, success: Callable[[T], U], failure: Callable[[Exception], U]) -> U: ...

    @overload
    def match(
        self, success: Callable[[T], Awaitable[U]], failure: Callable[[Exception], Awaitable[U]]
    ) -> Awaitable[U]: ...

    def match(
        self,
        success: Callable[[T], U] | Callable[[T], Awaitable[U]],
        failure: Callable[[Exception], U] | Callable[[Exception], Awaitable[U]],
    ) -> U | Awaitable[U]:
        """Pattern match on Result.

        Args:
            success: Function to handle success case
            failure: Function to handle failure case

        Returns:
            Result of the matching function

        """
        if isinstance(self._inner, Ok):
            return success(self._inner.value)
        return failure(self._inner.error)

    def __repr__(self) -> str:
        """String representation of Result."""
        if isinstance(self._inner, Ok):
            return f"Ok({repr(self._inner.value)})"
        return f"Err({repr(self._inner.error)})"


# Async support
class AsyncResult(Generic[T]):
    """Async wrapper for Result[T] to support async operations."""

    def __init__(self, awaitable: Awaitable[Result[T]]):
        """Initialize with an awaitable Result."""
        self._awaitable = awaitable

    async def get(self) -> Result[T]:
        """Await and get the Result."""
        return await self._awaitable

    def map(self, func: Callable[[T], U]) -> AsyncResult[U]:
        """Async map operation."""

        async def _map() -> Result[U]:
            result = await self._awaitable
            return result.map(func)

        return AsyncResult(_map())

    def flat_map(self, func: Callable[[T], Awaitable[Result[U]]]) -> AsyncResult[U]:
        """Async flat_map operation."""

        async def _flat_map() -> Result[U]:
            result = await self._awaitable
            if result.is_success():
                try:
                    return await func(result.unwrap())
                except Exception as e:
                    return Result.failure(e)
            return cast(Result[U], result)

        return AsyncResult(_flat_map())


# Utility functions
def collect_results(results: list[Result[T]]) -> Result[list[T]]:
    """Collect a list of Results into a Result of list.

    Args:
        results: List of Result[T]

    Returns:
        Ok(list) if all succeed, Err with first error otherwise

    """
    values = []
    for result in results:
        if result.is_failure():
            return cast(Result[list[T]], result)
        values.append(result.unwrap())
    return Result.success(values)


async def collect_async_results(results: list[Awaitable[Result[T]]]) -> Result[list[T]]:
    """Collect async Results into a Result of list.

    Args:
        results: List of awaitable Result[T]

    Returns:
        Ok(list) if all succeed, Err with first error otherwise

    """
    awaited_results = await asyncio.gather(*results)
    return collect_results(awaited_results)


def aggregate_errors(results: list[Result[T]]) -> Result[list[T]]:
    """Aggregate all errors from multiple Results.

    Args:
        results: List of Result[T]

    Returns:
        Ok(list) if all succeed, Err with AggregateError otherwise

    """
    values = []
    errors = []

    for result in results:
        if result.is_success():
            values.append(result.unwrap())
        else:
            errors.append(result.get_error())

    if errors:
        from src.core.exceptions import AgenticSystemError

        class AggregateError(AgenticSystemError):
            def __init__(self, errors: list[Exception]):
                super().__init__(
                    f"Multiple errors occurred: {len(errors)} failures",
                    details={"errors": [str(e) for e in errors]},
                )
                self.errors = errors

        return Result.failure(AggregateError(errors))

    return Result.success(values)


# Decorators for easy integration
def result_handler(func: Callable[..., T]) -> Callable[..., Result[T]]:
    """Decorator to convert functions to return Result[T].

    Args:
        func: Function to wrap

    Returns:
        Wrapped function returning Result[T]

    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
        try:
            return Result.success(func(*args, **kwargs))
        except Exception as e:
            return Result.failure(e)

    return wrapper


def async_result_handler(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[Result[T]]]:
    """Decorator for async functions to return Result[T].

    Args:
        func: Async function to wrap

    Returns:
        Wrapped async function returning Result[T]

    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result[T]:
        try:
            return Result.success(await func(*args, **kwargs))
        except Exception as e:
            return Result.failure(e)

    return wrapper


def unwrap_or_raise(result: Result[T]) -> T:
    """Helper to unwrap Result or raise the error.

    Args:
        result: Result to unwrap

    Returns:
        The success value

    Raises:
        The contained error if failure

    """
    return result.unwrap()


# Type aliases for common Result types
ResultStr = Result[str]
ResultDict = Result[dict[str, Any]]
ResultList = Result[list[Any]]
ResultNone = Result[None]
ResultBool = Result[bool]
