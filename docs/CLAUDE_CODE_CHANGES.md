# Claude Code Integration Changes

## Summary
Updated the Claude CLI client to work with **Claude Code** instead of the generic Claude CLI. The main change is using `claude -p` instead of `claude chat`.

## Changes Made

### 1. Updated Command Structure in `src/clients/claude_cli_client_robust.py`

#### Before:
```python
# Small prompts
cmd_parts = [self.cli_command, "chat"]

# Large prompts  
cmd_parts = [self.cli_command, "chat", "--file", temp_file_path]
```

#### After:
```python
# Small prompts
cmd_parts = [self.cli_command, "-p"]

# Large prompts
cmd_parts = [self.cli_command, "-p", f"@{temp_file_path}"]
```

### 2. Removed `--cwd` Flag Usage

#### Before:
```python
if workspace_dir:
    cmd_parts.extend(["--cwd", str(workspace_dir)])
```

#### After:
```python
# Claude Code handles workspace via subprocess cwd parameter
# No need to add --cwd flag
```

**Reason**: Claude Code may not support `--cwd` flag, so we use the subprocess `cwd` parameter instead.

### 3. Updated Test Assertions in `tests/test_claude_cli_client_robust.py`

#### Before:
```python
assert call_args[0][0] == "claude"
assert call_args[0][1] == "chat"
assert call_args[0][2] == "--file"
assert call_args[0][3] == temp_path
```

#### After:
```python
assert call_args[0][0] == "claude"
assert call_args[0][1] == "-p"
assert call_args[0][2] == f"@{temp_path}"
```

### 4. Updated Test Files

- **`test_claude_cli_simple.py`**: Updated to test `claude -p` instead of `claude chat`
- **`test_claude_code_integration.py`**: New test file specifically for Claude Code integration

## Key Differences: Claude CLI vs Claude Code

| Feature | Claude CLI | Claude Code |
|---------|------------|-------------|
| **Basic Command** | `claude chat` | `claude -p` |
| **File Input** | `claude chat --file filename` | `claude -p @filename` |
| **Workspace** | `claude chat --cwd /path` | Use subprocess `cwd` parameter |
| **JSON Output** | `claude chat --json` | `claude -p --json` (may not be supported) |
| **Stdin Input** | `echo "prompt" \| claude chat` | `echo "prompt" \| claude -p` |

## Testing

### Current Tests
All existing tests have been updated to work with the new command structure:
- `test_small_prompt_uses_stdin`
- `test_large_prompt_uses_temp_file`
- `test_json_command_line_args`

### New Tests
- `test_claude_code_integration.py` - Comprehensive integration test
- Updated `test_claude_cli_simple.py` - Direct CLI testing

### Running Tests
```bash
# Test the updated client
python test_claude_code_integration.py

# Run unit tests
python -m pytest tests/test_claude_cli_client_robust.py -v

# Test CLI directly
python test_claude_cli_simple.py
```

## Expected Behavior

### 1. Small Prompts (stdin)
```bash
# Command executed:
claude -p

# Input: via stdin
# Output: plain text response
```

### 2. Large Prompts (file mode)
```bash
# Command executed:
claude -p @/tmp/claude_prompt_12345.md

# Input: via temporary file
# Output: plain text response
```

### 3. Workspace Directory
```bash
# Command executed: 
claude -p

# Working directory: set via subprocess cwd parameter
# No --cwd flag needed
```

### 4. JSON Output (if supported)
```bash
# Command executed:
claude -p --json

# Output: JSON response (may not be supported by Claude Code)
```

## Migration Guide

### For Existing Code
No changes needed - the API remains the same:
```python
client = ClaudeCLIClient()
response = await client.create_code(prompt="...")
```

### For New Code
```python
from src.clients.claude_cli_client_robust import ClaudeCLIClient

# Basic usage
client = ClaudeCLIClient()
response = await client.create_code(prompt="Write a function")

# With workspace
response = await client.create_code(
    prompt="Write a function", 
    workspace_dir=Path("/workspace")
)

# With JSON output (may not work)
json_client = ClaudeCLIClient(json_output=True)
response = await json_client.create_code(prompt="...")
```

## Potential Issues

1. **JSON Output**: Claude Code may not support `--json` flag
2. **File Syntax**: The `@filename` syntax might not work
3. **Workspace Handling**: Need to verify subprocess `cwd` works correctly
4. **Timeout**: Claude Code may have different timeout behaviors

## Next Steps

1. **Test with real Claude Code**: Run the integration tests
2. **Verify JSON support**: Check if `--json` flag works
3. **Test file mode**: Verify `@filename` syntax works
4. **Update error handling**: Add Claude Code-specific error handling
5. **Performance testing**: Ensure no regressions in performance

## Files Modified

- `src/clients/claude_cli_client_robust.py` - Main client implementation
- `tests/test_claude_cli_client_robust.py` - Updated test assertions
- `test_claude_cli_simple.py` - Updated direct CLI testing
- `test_claude_code_integration.py` - New integration test