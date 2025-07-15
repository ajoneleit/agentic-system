# Result[T] Pattern Migration Guide

This guide helps you migrate existing exception-based code to use the Result[T] monad pattern for robust error handling.

## Overview

The Result[T] pattern provides type-safe error handling without exceptions. Every operation returns either `Ok(value)` or `Err(error)`, making error handling explicit and composable.

## Benefits

1. **Type Safety**: Errors are part of the function signature
2. **Explicit Error Handling**: Can't accidentally ignore errors
3. **Composability**: Chain operations with `map`, `flat_map`, etc.
4. **No Hidden Control Flow**: No unexpected exceptions
5. **Better Testing**: Errors are values, easier to test

## Quick Start

### Basic Usage

```python
from src.core.result import Result

# Instead of:
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Division by zero")
    return a / b

# Use:
def divide(a: float, b: float) -> Result[float]:
    if b == 0:
        return Result.failure(ValueError("Division by zero"))
    return Result.success(a / b)

# Usage:
result = divide(10, 2)
if result.is_success():
    print(f"Result: {result.unwrap()}")  # Result: 5.0
else:
    print(f"Error: {result.get_error()}")
```

### Async Functions

```python
from src.core.result import Result, async_result_handler

# Instead of:
async def fetch_data(url: str) -> dict:
    response = await http_client.get(url)
    if response.status != 200:
        raise APIError(f"HTTP {response.status}")
    return response.json()

# Use:
async def fetch_data(url: str) -> Result[dict]:
    response = await http_client.get(url)
    if response.status != 200:
        return Result.failure(APIError(f"HTTP {response.status}"))
    return Result.success(response.json())

# Or with decorator:
@async_result_handler
async def fetch_data(url: str) -> dict:
    response = await http_client.get(url)
    if response.status != 200:
        raise APIError(f"HTTP {response.status}")
    return response.json()
```

## Migration Patterns

### Pattern 1: Gradual Migration with Decorators

Use decorators to wrap existing functions without changing their implementation:

```python
from src.core.result_integration import exception_to_result, async_exception_to_result

# Existing code:
def process_data(data: str) -> dict:
    if not data:
        raise ValueError("Empty data")
    return json.loads(data)

# Step 1: Add decorator
@exception_to_result
def process_data(data: str) -> dict:
    if not data:
        raise ValueError("Empty data")
    return json.loads(data)

# Now it returns Result[dict]
result = process_data('{"key": "value"}')
```

### Pattern 2: Chaining Operations

Replace try-catch chains with Result chains:

```python
# Instead of:
try:
    user = get_user(user_id)
    validate_permissions(user)
    project = load_project(project_id)
    code = generate_code(project)
except UserNotFound as e:
    handle_user_error(e)
except PermissionError as e:
    handle_permission_error(e)
except Exception as e:
    handle_generic_error(e)

# Use:
from src.core.result_integration import ResultChain

result = (
    ResultChain(get_user(user_id))
    .then(lambda user: validate_permissions(user))
    .then(lambda _: load_project(project_id))
    .then(lambda project: generate_code(project))
    .recover(lambda e: handle_specific_error(e))
    .get()
)
```

### Pattern 3: Parallel Operations

Handle multiple async operations:

```python
# Instead of:
try:
    results = await asyncio.gather(
        fetch_data(url1),
        fetch_data(url2),
        fetch_data(url3),
        return_exceptions=True
    )
    # Manual error checking...
except Exception as e:
    # Handle errors...

# Use:
from src.core.result_integration import execute_parallel_with_results

operations = [
    lambda: fetch_data(url1),
    lambda: fetch_data(url2),
    lambda: fetch_data(url3),
]
result = await execute_parallel_with_results(operations)

if result.is_success():
    data_list = result.unwrap()
else:
    error = result.get_error()
```

## Agent Migration Example

### Before (Exception-based)

```python
class CodeGeneratorAgent(BaseSubAgent):
    async def _execute_task_impl(self, task: Task, context: TaskContext) -> List[Artifact]:
        # Validate input
        if not task.description:
            raise ValueError("Task description required")
        
        # Generate code
        try:
            code = await self._generate_code(task)
        except APIError as e:
            logger.error(f"Generation failed: {e}")
            raise TaskExecutionError(task.id, self.id, str(e))
        
        # Create artifact
        artifact = Artifact(
            id=uuid4(),
            name="code.py",
            type=ArtifactType.CODE,
            content=code
        )
        
        return [artifact]
```

### After (Result-based)

```python
class CodeGeneratorAgent(BaseSubAgent):
    async def _execute_task_impl(self, task: Task, context: TaskContext) -> List[Artifact]:
        # Convert to Result-based flow
        result = await (
            AsyncResultChain(self._validate_input(task))
            .then(lambda _: self._generate_code(task))
            .then(lambda code: self._create_artifact(code, task))
            .get()
        )
        
        return result.unwrap_or_else(
            lambda e: self._handle_error(e, task)
        )
    
    async def _validate_input(self, task: Task) -> Result[None]:
        if not task.description:
            return Result.failure(ValueError("Task description required"))
        return Result.success(None)
    
    async def _generate_code(self, task: Task) -> Result[str]:
        try:
            code = await self.api_client.generate(task.description)
            return Result.success(code)
        except APIError as e:
            return Result.failure(e)
```

## Best Practices

### 1. Use Specific Error Types

```python
# Good
return Result.failure(ValidationError("Invalid email format"))

# Avoid
return Result.failure(Exception("Invalid email"))
```

### 2. Leverage Type Hints

```python
from typing import List
from src.core.result import Result, ResultList

def parse_numbers(text: str) -> Result[List[int]]:
    try:
        numbers = [int(x) for x in text.split()]
        return Result.success(numbers)
    except ValueError as e:
        return Result.failure(e)
```

### 3. Use Pattern Matching

```python
# Use match for clear control flow
result = divide(10, 2)

value = result.match(
    success=lambda x: f"Result: {x}",
    failure=lambda e: f"Error: {e}"
)
```

### 4. Error Recovery

```python
# Provide fallbacks
config = (
    load_config_from_file()
    .or_else(lambda _: load_config_from_env())
    .or_else(lambda _: Result.success(DEFAULT_CONFIG))
    .unwrap()
)
```

### 5. Logging and Monitoring

```python
from src.core.result_integration import log_result_errors

result = (
    perform_operation()
    .map(log_result_errors("MyComponent", "operation"))
    .flat_map(process_further)
)
```

## Common Pitfalls

### 1. Forgetting to Handle Errors

```python
# Bad - might panic
value = some_operation().unwrap()

# Good - handle the error case
value = some_operation().unwrap_or(default_value)
# Or
result = some_operation()
if result.is_success():
    value = result.unwrap()
else:
    handle_error(result.get_error())
```

### 2. Nested Result Types

```python
# Avoid Result[Result[T]]
# Use flat_map instead of map when the operation returns Result

# Bad
result = get_user(id).map(lambda u: validate_user(u))  # Result[Result[User]]

# Good
result = get_user(id).flat_map(lambda u: validate_user(u))  # Result[User]
```

### 3. Not Capturing Tracebacks

```python
# Good - captures traceback for debugging
return Result.failure(error, capture_traceback=True)

# When logging
if result.is_failure():
    logger.error(
        "Operation failed",
        error=str(result.get_error()),
        traceback=result.get_traceback()
    )
```

## Testing with Result[T]

Testing becomes more straightforward:

```python
import pytest
from src.core.result import Result

def test_divide_success():
    result = divide(10, 2)
    assert result.is_success()
    assert result.unwrap() == 5.0

def test_divide_by_zero():
    result = divide(10, 0)
    assert result.is_failure()
    assert isinstance(result.get_error(), ValueError)
    assert "Division by zero" in str(result.get_error())

# Test error propagation
def test_operation_chain():
    result = (
        Result.success(10)
        .map(lambda x: x * 2)
        .flat_map(lambda x: divide(x, 0))  # This fails
        .map(lambda x: x + 1)  # This is skipped
    )
    
    assert result.is_failure()
    assert isinstance(result.get_error(), ValueError)
```

## Integration with Existing Systems

### Bridging with Exception-based Code

```python
from src.core.result import unwrap_or_raise

# When calling Result-returning functions from exception-based code
def legacy_function():
    # This will raise if the Result is a failure
    value = unwrap_or_raise(new_result_function())
    return value * 2

# When calling exception-based functions from Result code
def new_function() -> Result[int]:
    try:
        value = legacy_exception_function()
        return Result.success(value)
    except Exception as e:
        return Result.failure(e)
```

## Performance Considerations

1. **Minimal Overhead**: Result[T] adds minimal runtime overhead
2. **Stack Traces**: Capturing tracebacks has a small cost; disable in hot paths
3. **Memory**: Each Result object is small (similar to Optional)

## Migration Checklist

- [ ] Identify error-prone functions to migrate first
- [ ] Add Result import to modules
- [ ] Start with leaf functions (no dependencies)
- [ ] Use decorators for gradual migration
- [ ] Update function signatures and documentation
- [ ] Migrate callers to handle Result types
- [ ] Add comprehensive tests
- [ ] Update error logging and monitoring
- [ ] Remove try-catch blocks where Result is used
- [ ] Document new error handling patterns for team

## Resources

- `src/core/result.py` - Core Result[T] implementation
- `src/core/result_integration.py` - Integration utilities
- `src/agents/result_based_agent.py` - Example implementations
- `tests/test_result.py` - Comprehensive tests