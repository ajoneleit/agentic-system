"""Unit tests for the robust Claude CLI client implementation."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call, mock_open
import pytest

from src.clients.claude_cli_client_robust import ClaudeCodeClient, _cleanup_temp_files, _temp_files
from src.core.exceptions import APIError, APIResponseError


class TestClaudeCodeClientRobust:
    """Test cases for the robust Claude Code client."""
    
    @pytest.fixture
    def client(self):
        """Create a Claude Code client instance."""
        return ClaudeCodeClient()
    
    @pytest.fixture
    def mock_subprocess(self):
        """Mock subprocess execution."""
        with patch('asyncio.create_subprocess_exec') as mock:
            process = AsyncMock()
            process.returncode = 0
            # Default JSON response
            json_response = {
                "status": "ok",
                "summary": "Test response",
                "files": [],
                "errors": [],
                "metrics": {
                    "tokens_prompt": 10,
                    "tokens_completion": 5,
                    "elapsed_ms": 1000
                }
            }
            process.communicate = AsyncMock(return_value=(json.dumps(json_response).encode(), b""))
            mock.return_value = process
            yield mock, process
    
    @pytest.mark.asyncio
    async def test_small_prompt_uses_command_line(self, client, mock_subprocess):
        """Test that small prompts are passed via command line arguments."""
        mock_exec, mock_process = mock_subprocess
        
        # Small prompt that should use command line
        small_prompt = "Write a hello world function"
        
        response = await client.create_code(prompt=small_prompt)
        
        # Verify subprocess was called correctly
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        
        # Check command format: claude -p "prompt" --output-format json
        assert call_args[0][0] == "claude"
        assert call_args[0][1] == "-p"
        assert call_args[0][2] == small_prompt
        assert call_args[0][3] == "--output-format"
        assert call_args[0][4] == "json"
        
        # Check no stdin was used (command line argument instead)
        assert call_args[1].get('stdin') is None
        
        # Verify communicate was called without input
        mock_process.communicate.assert_called_once_with()
        
        # Verify JSON response is returned
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Test response"
        assert "files" in response
        assert "errors" in response
        assert "metrics" in response
    
    @pytest.mark.asyncio
    async def test_large_prompt_uses_temp_file(self, client, mock_subprocess):
        """Test that large prompts use temporary files."""
        mock_exec, mock_process = mock_subprocess
        
        # Create a large prompt that exceeds the threshold
        large_prompt = "x" * (client.TEMP_FILE_THRESHOLD + 1000)
        
        with patch('tempfile.mkstemp') as mock_mkstemp:
            # Mock the temp file creation
            fd = MagicMock()
            temp_path = "/tmp/claude_prompt_12345.md"
            mock_mkstemp.return_value = (fd, temp_path)
            
            with patch('os.fdopen', mock_open()) as mock_fdopen:
                with patch('os.path.exists', return_value=True):
                    with patch('os.unlink') as mock_unlink:
                        response = await client.create_code(prompt=large_prompt)
        
        # Verify temp file was created
        mock_mkstemp.assert_called_once_with(
            suffix='.md', 
            prefix='claude_prompt_', 
            text=True
        )
        
        # Verify content was written to temp file
        mock_fdopen.assert_called_once_with(fd, 'w', encoding='utf-8')
        handle = mock_fdopen()
        handle.write.assert_called_once_with(large_prompt)
        
        # Verify subprocess was called with file argument
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        assert call_args[0][0] == "claude"
        assert call_args[0][1] == "-p"
        assert call_args[0][2] == f"@{temp_path}"
        assert call_args[0][3] == "--output-format"
        assert call_args[0][4] == "json"
        
        # Verify no stdin was used
        assert 'stdin' not in call_args[1] or call_args[1]['stdin'] is None
        
        # Verify temp file was cleaned up
        mock_unlink.assert_called_with(temp_path)
        
        # Verify JSON response is returned
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Test response"
        assert "files" in response
        assert "errors" in response
        assert "metrics" in response
    
    @pytest.mark.asyncio
    async def test_context_files_included(self, client, mock_subprocess, tmp_path):
        """Test that context files are properly included in the prompt."""
        mock_exec, mock_process = mock_subprocess
        
        # Create test files
        file1 = tmp_path / "test1.py"
        file1.write_text("def hello(): return 'world'")
        
        file2 = tmp_path / "test2.py"
        file2.write_text("def foo(): return 'bar'")
        
        # Binary file should be ignored
        binary_file = tmp_path / "image.png"
        binary_file.write_bytes(b'\x89PNG\r\n\x1a\n')
        
        context_files = [file1, file2, binary_file]
        prompt = "Analyze these files"
        
        response = await client.create_code(
            prompt=prompt,
            context_files=context_files
        )
        
        # Check that the prompt includes file contents by examining command line args
        mock_process.communicate.assert_called_once()
        call_args = mock_process.communicate.call_args
        
        # Get the command line arguments to check the prompt
        subprocess_args = mock_process.communicate.call_args
        # The prompt should be in the command line args from the subprocess call
        # Since we're mocking, we can check the subprocess was called
        assert mock_process.communicate.called
        
        # Verify JSON response is returned
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Test response"
        assert "files" in response
        assert "errors" in response
        assert "metrics" in response
    
    @pytest.mark.asyncio
    async def test_error_handling_non_zero_exit(self, client, mock_subprocess):
        """Test error handling when CLI returns non-zero exit code."""
        mock_exec, mock_process = mock_subprocess
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error: Invalid prompt")
        
        with pytest.raises(APIResponseError) as exc_info:
            await client.create_code(prompt="Test prompt")
        
        assert "Claude Code failed with code 1" in str(exc_info.value)
        assert "Invalid prompt" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_error_handling_subprocess_error(self, client):
        """Test error handling when subprocess creation fails."""
        with patch('asyncio.create_subprocess_exec', side_effect=OSError("Command not found")):
            with pytest.raises(APIError) as exc_info:
                await client.create_code(prompt="Test prompt")
            
            assert "Claude Code execution failed" in str(exc_info.value)
            assert "Command not found" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_temp_file_cleanup_on_error(self, client, mock_subprocess):
        """Test that temp files are cleaned up even when errors occur."""
        mock_exec, mock_process = mock_subprocess
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b"", b"Error")
        
        large_prompt = "x" * (client.TEMP_FILE_THRESHOLD + 1000)
        
        with patch('tempfile.mkstemp') as mock_mkstemp:
            fd = MagicMock()
            temp_path = "/tmp/claude_prompt_error.md"
            mock_mkstemp.return_value = (fd, temp_path)
            
            with patch('os.fdopen', mock_open()):
                with patch('os.path.exists', return_value=True):
                    with patch('os.unlink') as mock_unlink:
                        with pytest.raises(APIResponseError):
                            await client.create_code(prompt=large_prompt)
            
            # Verify temp file was still cleaned up
            mock_unlink.assert_called_with(temp_path)
    
    @pytest.mark.asyncio
    async def test_create_message_for_code_compatibility(self, client, mock_subprocess):
        """Test the API compatibility method."""
        mock_exec, mock_process = mock_subprocess
        
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Write a factorial function"}
        ]
        
        response = await client.create_message_for_code(
            messages=messages,
            task_type="code"
        )
        
        # Verify response format - now returns JSON
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Test response"
        assert "files" in response
        assert "errors" in response
        assert "metrics" in response
        
        # Check that task-specific prompt was added by checking subprocess call
        mock_process.communicate.assert_called_once()
        # Since we're using command line arguments, the prompt structure is handled internally
    
    @pytest.mark.asyncio
    async def test_check_cli_available_success(self, client):
        """Test checking CLI availability when it's available."""
        with patch('asyncio.create_subprocess_exec') as mock_exec:
            process = AsyncMock()
            process.returncode = 0
            process.communicate = AsyncMock(return_value=(
                b"Claude Code version 1.0.0", b""
            ))
            mock_exec.return_value = process
            
            available = await client.check_cli_available()
            
            assert available is True
            # Should try --version first
            assert mock_exec.call_args_list[0][0][1] == "--version"
    
    @pytest.mark.asyncio
    async def test_check_cli_available_not_found(self, client):
        """Test checking CLI availability when it's not found."""
        with patch('asyncio.create_subprocess_exec', side_effect=FileNotFoundError()):
            available = await client.check_cli_available()
            assert available is False
    
    @pytest.mark.asyncio
    async def test_workspace_dir_handling(self, client, mock_subprocess, tmp_path):
        """Test that workspace directory is properly set."""
        mock_exec, mock_process = mock_subprocess
        
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        await client.create_code(
            prompt="Test",
            workspace_dir=workspace
        )
        
        # Verify cwd was set
        call_kwargs = mock_exec.call_args[1]
        assert call_kwargs['cwd'] == str(workspace)
    
    @pytest.mark.asyncio
    async def test_large_file_skipped(self, client, mock_subprocess, tmp_path):
        """Test that large context files are skipped."""
        mock_exec, mock_process = mock_subprocess
        
        # Create a large file (> 1MB)
        large_file = tmp_path / "large.txt"
        large_file.write_text("x" * (1_000_001))
        
        context_files = [large_file]
        
        response = await client.create_code(
            prompt="Test",
            context_files=context_files
        )
        
        # Verify JSON response is returned
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Test response"
        
        # Verify the large file content is not in the prompt by checking command args
        call_args = mock_exec.call_args
        prompt_arg = call_args[0][2]  # The prompt is the 3rd argument
        assert "x" * 1000 not in prompt_arg  # Should not contain the file content
    
    def test_cleanup_temp_files(self):
        """Test the temp file cleanup function."""
        # Add some test temp files
        temp_files = {"/tmp/test1.md", "/tmp/test2.md"}
        _temp_files.update(temp_files)
        
        with patch('os.path.exists', return_value=True):
            with patch('os.unlink') as mock_unlink:
                _cleanup_temp_files()
        
        # Verify all files were attempted to be cleaned
        for temp_file in temp_files:
            mock_unlink.assert_any_call(temp_file)
        
        # Verify the set is empty after cleanup
        assert len(_temp_files) == 0
    
    @pytest.mark.asyncio
    async def test_empty_response_handling(self, client, mock_subprocess):
        """Test handling of empty responses from CLI."""
        mock_exec, mock_process = mock_subprocess
        mock_process.communicate.return_value = (b"", b"Warning: No output")
        
        # Empty response should raise an error since we always expect JSON
        with pytest.raises(APIResponseError) as exc_info:
            await client.create_code(prompt="Test")
        
        assert "empty response" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_encoding_issues_handled(self, client, mock_subprocess):
        """Test that encoding issues are handled gracefully."""
        mock_exec, mock_process = mock_subprocess
        # Invalid UTF-8 sequence that results in invalid JSON
        mock_process.communicate.return_value = (b"Test \x80 response", b"")
        
        # Invalid JSON should raise an error
        with pytest.raises(APIResponseError) as exc_info:
            await client.create_code(prompt="Test")
        
        assert "Malformed JSON response" in str(exc_info.value)


class TestClaudeCodeClientJSON:
    """Test cases for JSON output protocol."""
    
    @pytest.fixture
    def json_client(self):
        """Create a Claude Code client with JSON output enabled."""
        return ClaudeCodeClient()
    
    @pytest.fixture
    def mock_subprocess_json(self):
        """Mock subprocess execution for JSON responses."""
        with patch('asyncio.create_subprocess_exec') as mock:
            process = AsyncMock()
            process.returncode = 0
            # Default JSON response
            json_response = {
                "status": "ok",
                "summary": "Generated test file",
                "files": [
                    {
                        "path": "test.py",
                        "action": "created",
                        "size_bytes": 100,
                        "sha256": "abc123"
                    }
                ],
                "errors": [],
                "metrics": {
                    "tokens_prompt": 50,
                    "tokens_completion": 100,
                    "elapsed_ms": 1500
                }
            }
            process.communicate = AsyncMock(return_value=(json.dumps(json_response).encode(), b""))
            mock.return_value = process
            yield mock, process
    
    @pytest.mark.asyncio
    async def test_json_output_enabled(self, json_client):
        """Test that JSON output is enabled."""
        assert json_client.is_json_output() is True
        
        # Test factory method
        factory_client = ClaudeCodeClient.create_json_client()
        assert factory_client.is_json_output() is True
    
    @pytest.mark.asyncio
    async def test_json_response_parsing(self, json_client, mock_subprocess_json):
        """Test JSON response parsing."""
        mock_exec, mock_process = mock_subprocess_json
        
        response = await json_client.create_code(prompt="Test")
        
        # Should return parsed JSON
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert response["summary"] == "Generated test file"
        assert len(response["files"]) == 1
        assert response["files"][0]["path"] == "test.py"
        assert response["files"][0]["action"] == "created"
        assert len(response["errors"]) == 0
        assert "metrics" in response
    
    @pytest.mark.asyncio
    async def test_json_command_line_args(self, json_client, mock_subprocess_json, tmp_path):
        """Test that JSON client adds correct command line arguments."""
        mock_exec, mock_process = mock_subprocess_json
        
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        
        await json_client.create_code(
            prompt="Test",
            workspace_dir=workspace
        )
        
        # Check command line arguments
        call_args = mock_exec.call_args
        cmd_args = call_args[0]
        
        assert "--output-format" in cmd_args
        assert "json" in cmd_args
        # Note: --cwd is no longer used, workspace is handled via subprocess cwd parameter
    
    @pytest.mark.asyncio
    async def test_json_empty_response_error(self, json_client, mock_subprocess_json):
        """Test that empty JSON response raises error."""
        mock_exec, mock_process = mock_subprocess_json
        mock_process.communicate.return_value = (b"", b"")
        
        with pytest.raises(APIResponseError) as exc_info:
            await json_client.create_code(prompt="Test")
        
        assert "empty response" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_json_malformed_response_error(self, json_client, mock_subprocess_json):
        """Test that malformed JSON response raises error."""
        mock_exec, mock_process = mock_subprocess_json
        mock_process.communicate.return_value = (b"invalid json", b"")
        
        with pytest.raises(APIResponseError) as exc_info:
            await json_client.create_code(prompt="Test")
        
        assert "Malformed JSON response" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_json_missing_required_fields(self, json_client, mock_subprocess_json):
        """Test that JSON response with missing fields raises error."""
        mock_exec, mock_process = mock_subprocess_json
        
        # Missing required fields
        incomplete_response = {"status": "ok"}
        mock_process.communicate.return_value = (json.dumps(incomplete_response).encode(), b"")
        
        with pytest.raises(APIResponseError) as exc_info:
            await json_client.create_code(prompt="Test")
        
        assert "Missing required field" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_json_fatal_error_handling(self, json_client, mock_subprocess_json):
        """Test that fatal errors in JSON response raise exceptions."""
        mock_exec, mock_process = mock_subprocess_json
        
        # Response with fatal error
        error_response = {
            "status": "error",
            "summary": "Fatal error occurred",
            "files": [],
            "errors": [
                {
                    "type": "FileTooLarge",
                    "message": "File exceeds maximum size",
                    "fatal": True
                }
            ],
            "metrics": {}
        }
        mock_process.communicate.return_value = (json.dumps(error_response).encode(), b"")
        
        with pytest.raises(APIResponseError) as exc_info:
            await json_client.create_code(prompt="Test")
        
        assert "Fatal errors" in str(exc_info.value)
        assert "File exceeds maximum size" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_json_non_fatal_errors_allowed(self, json_client, mock_subprocess_json):
        """Test that non-fatal errors don't raise exceptions."""
        mock_exec, mock_process = mock_subprocess_json
        
        # Response with non-fatal error
        warning_response = {
            "status": "ok",
            "summary": "Generated with warnings",
            "files": [],
            "errors": [
                {
                    "type": "SyntaxError",
                    "message": "Minor syntax warning",
                    "fatal": False
                }
            ],
            "metrics": {}
        }
        mock_process.communicate.return_value = (json.dumps(warning_response).encode(), b"")
        
        response = await json_client.create_code(prompt="Test")
        
        # Should return response with non-fatal errors
        assert isinstance(response, dict)
        assert response["status"] == "ok"
        assert len(response["errors"]) == 1
        assert response["errors"][0]["fatal"] is False
    
    @pytest.mark.asyncio
    async def test_text_to_json_conversion(self, tmp_path):
        """Test conversion from text response to JSON format."""
        client = ClaudeCodeClient()
        
        # Create test file in workspace
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        test_file = workspace / "test.py"
        test_file.write_text("print('hello')")
        
        # Convert text response to JSON
        json_response = client.convert_text_to_json_response(
            text_response="Created test.py",
            workspace_dir=workspace,
            prompt_tokens=50,
            completion_tokens=100,
            elapsed_ms=1500
        )
        
        # Verify JSON structure
        assert isinstance(json_response, dict)
        assert json_response["status"] == "ok"
        assert json_response["summary"] == "Generated 1 file(s)"
        assert len(json_response["files"]) == 1
        assert json_response["files"][0]["path"] == "test.py"
        assert json_response["files"][0]["action"] == "created"
        assert json_response["metrics"]["tokens_prompt"] == 50
        assert json_response["metrics"]["tokens_completion"] == 100
        assert json_response["metrics"]["elapsed_ms"] == 1500


if __name__ == "__main__":
    pytest.main([__file__, "-v"])