# Claude CLI "Argument Too Long" Fix Documentation

## Overview

This document describes the fix for the `OSError [Errno 7] Argument list too long` error that occurs when using the Claude CLI with large prompts (15k+ tokens).

## Problem

The original `claude_cli_client.py` implementation attempted to pass prompts via stdin, but the error still occurred because:

1. The OS has limits on the total size of arguments + environment variables passed to a process
2. Large environment variables or other factors can reduce the available space
3. Even though the prompt was sent via stdin, the command line construction itself could exceed limits

## Solution

The robust implementation (`claude_cli_client_robust.py`) implements a dual-mode approach:

### 1. Small Prompts (< 4KB)
- Uses stdin directly with minimal command arguments
- Command: `claude chat` (no additional flags that could increase size)
- Prompt is passed via stdin using `process.communicate(input=prompt.encode())`

### 2. Large Prompts (≥ 4KB)
- Creates a secure temporary file using `tempfile.mkstemp()`
- Writes the prompt to the temporary file
- Uses the `--file` flag: `claude chat --file /tmp/claude_prompt_XXX.md`
- No stdin is used, avoiding any size limitations

## Key Features

### Automatic Threshold Detection
```python
use_temp_file = len(full_prompt) > self.TEMP_FILE_THRESHOLD  # 4000 chars
```

### Secure Temporary File Handling
- Uses `tempfile.mkstemp()` for secure file creation
- Tracks all temp files for cleanup
- Implements cleanup in:
  - Normal execution flow (finally block)
  - Process exit (atexit handler)
  - Signal handlers (SIGTERM, SIGINT)

### Enhanced Error Handling
- Detailed error messages with return codes
- Graceful handling of encoding issues
- Proper cleanup even on errors

### Performance Optimizations
- Skips binary files in context
- Ignores large files (> 1MB)
- Filters out common non-source directories

## Migration Guide

### 1. Update Existing Code

#### Manual Update
Change your imports from:
```python
from src.clients.claude_cli_client import ClaudeCLIClient
```

To:
```python
from src.clients.claude_cli_client_robust import ClaudeCLIClient
```

#### Automated Migration
Run the migration script:
```bash
python scripts/migrate_to_robust_cli_client.py
```

### 2. No API Changes Required

The robust client maintains the same API, so no code changes are needed beyond the import.

### 3. Testing

Run the test suite to verify the fix:
```bash
# Run specific tests for the robust client
pytest tests/test_claude_cli_client_robust.py -v

# Run all tests to ensure compatibility
pytest tests/
```

## Usage Examples

### Basic Usage
```python
from src.clients.claude_cli_client_robust import ClaudeCLIClient

client = ClaudeCLIClient()

# Small prompt - uses stdin
response = await client.create_code(
    prompt="Write a hello world function"
)

# Large prompt - automatically uses temp file
large_prompt = "Analyze this code:\n" + ("x" * 10000)
response = await client.create_code(prompt=large_prompt)
```

### With Context Files
```python
context_files = [
    Path("src/main.py"),
    Path("src/utils.py"),
    Path("tests/test_main.py")
]

response = await client.create_code(
    prompt="Refactor this code for better performance",
    context_files=context_files,
    workspace_dir=Path("./workspace")
)
```

## Environment Considerations

### Local Development
- Temp files are created in the system temp directory
- Automatic cleanup ensures no file accumulation

### CI/CD Environments
- Works in containerized environments
- Handles restricted temp directories gracefully
- No special configuration required

## Troubleshooting

### Issue: "Command not found"
**Solution**: Ensure Claude CLI is installed and in PATH:
```bash
which claude
claude --version
```

### Issue: "Permission denied" on temp files
**Solution**: Check temp directory permissions:
```python
import tempfile
print(tempfile.gettempdir())  # Should be writable
```

### Issue: Large files still causing issues
**Solution**: Adjust the threshold if needed:
```python
client = ClaudeCLIClient()
client.TEMP_FILE_THRESHOLD = 2000  # Lower threshold for testing
```

## Performance Characteristics

- **Small prompts**: No performance impact (same as original)
- **Large prompts**: Minimal overhead from temp file I/O
- **Temp file creation**: ~1-5ms
- **Cleanup overhead**: Negligible

## Security Considerations

1. **Temp File Security**:
   - Uses `mkstemp()` with secure permissions (600)
   - Files are created with restrictive permissions
   - Immediate cleanup after use

2. **No Sensitive Data Leakage**:
   - Temp files are always cleaned up
   - Signal handlers ensure cleanup on interruption

## Future Improvements

1. **Configurable Threshold**: Make `TEMP_FILE_THRESHOLD` configurable via environment variable
2. **Compression**: For very large contexts, consider compression
3. **Streaming**: Implement streaming responses for real-time output
4. **Caching**: Cache responses for identical prompts

## References

- [Linux ARG_MAX Limits](https://www.in-ulm.de/~mascheck/various/argmax/)
- [Python tempfile Documentation](https://docs.python.org/3/library/tempfile.html)
- [Claude CLI Documentation](https://github.com/anthropics/claude-cli)