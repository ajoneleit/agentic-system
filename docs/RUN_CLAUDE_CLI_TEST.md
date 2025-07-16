# Claude CLI Integration Test

## Overview
This document provides instructions to test if the Claude CLI actually works when called by the program.

## Prerequisites
1. **Claude CLI must be installed**:
   ```bash
   # Check if installed
   which claude
   claude --version
   ```

2. **Authentication must be configured**:
   ```bash
   # Check if authenticated
   claude auth status
   ```

3. **Network access to Claude API**

## Test Commands

### 1. Basic CLI Test
```bash
# Run the comprehensive test
python test_real_claude_cli.py
```

### 2. Manual CLI Test
```bash
# Test CLI directly
claude chat --help

# Test simple command
echo "Write a hello world function" | claude chat

# Test JSON output
echo "Write a hello world function" | claude chat --json
```

### 3. Test with Workspace
```bash
# Create test workspace
mkdir -p /tmp/test_workspace
cd /tmp/test_workspace

# Test with workspace
echo "Create a Python calculator" | claude chat --cwd /tmp/test_workspace
```

## Expected Behavior

### 1. CLI Availability Check
- `client.check_cli_available()` should return `True`
- Should not throw `FileNotFoundError`

### 2. Simple Text Response
- `client.create_code()` should return a string response
- Response should contain code (e.g., "def", "return")
- Should complete within reasonable time (< 30s)

### 3. JSON Response
- `ClaudeCLIClient(json_output=True)` should return dict
- JSON should have keys: `status`, `summary`, `files`, `errors`, `metrics`
- `status` should be "ok" for successful responses

### 4. Workspace Integration
- Should accept `workspace_dir` parameter
- Should set `--cwd` flag in command
- May create files in workspace directory

### 5. Large Prompt Handling
- Prompts > 64KB should use `--file` flag
- Should create temporary files automatically
- Should clean up temporary files after execution

## Current Implementation Analysis

Based on the code in `src/clients/claude_cli_client_robust.py`:

### Command Structure
```python
# Small prompts (stdin)
["claude", "chat"]

# Large prompts (file)
["claude", "chat", "--file", "/tmp/claude_prompt_xyz.md"]

# With workspace
["claude", "chat", "--cwd", "/path/to/workspace"]

# With JSON output
["claude", "chat", "--json"]
```

### Key Methods
1. `check_cli_available()` - Tests `claude --version`
2. `create_code()` - Main method for sending prompts
3. `create_message_for_code()` - API compatibility wrapper

### Error Handling
- `FileNotFoundError` → CLI not installed
- `APIResponseError` → CLI returned error
- `APIError` → Subprocess execution failed
- Timeout after 300 seconds (5 minutes)

## Common Issues

### 1. CLI Not Found
```
FileNotFoundError: [Errno 2] No such file or directory: 'claude'
```
**Solution**: Install Claude CLI

### 2. Authentication Issues
```
Error: Authentication required
```
**Solution**: Configure authentication with `claude auth login`

### 3. Permission Prompts
```
Do you want to create files? (y/n)
```
**Solution**: CLI may need non-interactive flags (not currently implemented)

### 4. Network Issues
```
Error: Connection timeout
```
**Solution**: Check network connectivity and API status

## Testing Results

Run the test and check:

- [ ] CLI availability check passes
- [ ] Simple text prompt returns valid response
- [ ] JSON output returns structured data
- [ ] Workspace integration works
- [ ] Large prompts handled correctly
- [ ] No hanging or timeout issues
- [ ] Temporary files cleaned up properly

## Troubleshooting

If tests fail:

1. **Check CLI installation**: `claude --version`
2. **Check authentication**: `claude auth status`
3. **Test manually**: `echo "test" | claude chat`
4. **Check logs**: Look for error messages in stderr
5. **Verify network**: Test API connectivity
6. **Check permissions**: Ensure CLI can create files

## Next Steps

If Claude CLI integration is not working:

1. **Mock the CLI**: Use subprocess mocking for development
2. **Add fallback**: Implement direct API calls as backup
3. **Improve error handling**: Add specific error messages
4. **Add configuration**: Allow custom CLI path/flags
5. **Add validation**: Check response format before processing

## Files Created

- `test_real_claude_cli.py` - Comprehensive integration test
- `test_claude_cli_simple.py` - Simple subprocess test
- `test_claude_cli_manual.py` - Manual test with detailed output

Run any of these to test Claude CLI integration.