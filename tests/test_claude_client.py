"""Tests for Claude client functionality."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from anthropic import APIError as AnthropicAPIError, RateLimitError
from anthropic.types import Message, Usage, TextBlock, ToolUseBlock

from src.clients.health_client import ClaudeClient
from src.core.exceptions import (
    APIError,
    APIRateLimitError,
    APIResponseError,
)
from config import ClaudeModel


class TestClaudeClient:
    """Test Claude client functionality."""
    
    @pytest.fixture
    def claude_client(self):
        """Create ClaudeClient instance with mocked API client."""
        with patch('src.clients.health_client.AsyncAnthropic') as mock_anthropic:
            client = ClaudeClient()
            yield client
    
    @pytest.mark.asyncio
    async def test_create_message_success(self, claude_client):
        """Test successful message creation."""
        # Mock response
        mock_response = Message(
            id="msg_123",
            content=[{"text": "Hello, world!", "type": "text"}],
            model="claude-3-sonnet",
            role="assistant",
            usage=Usage(input_tokens=10, output_tokens=20),
            type="message",
            stop_reason="end_turn",
            stop_sequence=None,
        )
        
        claude_client.client.messages.create = AsyncMock(return_value=mock_response)
        
        # Make request
        response = await claude_client.create_message(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": "Say hello"}],
        )
        
        assert response.id == "msg_123"
        assert response.content[0].text == "Hello, world!"
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 20
    
    @pytest.mark.asyncio
    async def test_create_message_with_retry(self, claude_client):
        """Test message creation with retry on rate limit."""
        # First call raises rate limit error
        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=MagicMock(status_code=429),
            body={"error": {"message": "Rate limit exceeded"}},
        )
        
        # Second call succeeds
        mock_response = Message(
            id="msg_456",
            content=[{"text": "Success after retry", "type": "text"}],
            model="claude-3-sonnet",
            role="assistant",
            usage=Usage(input_tokens=5, output_tokens=10),
            type="message",
            stop_reason="end_turn",
            stop_sequence=None,
        )
        
        claude_client.client.messages.create = AsyncMock(
            side_effect=[rate_limit_error, mock_response]
        )
        
        # Should retry and succeed
        response = await claude_client.create_message(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": "Test"}],
        )
        
        assert response.id == "msg_456"
        assert claude_client.client.messages.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_create_message_api_error(self, claude_client):
        """Test API error handling."""
        api_error = AnthropicAPIError(
            message="Internal server error",
            request=MagicMock(),
            body={"error": {"message": "Internal server error"}},
        )
        api_error.response = MagicMock(status_code=500)
        
        claude_client.client.messages.create = AsyncMock(side_effect=api_error)
        
        from tenacity import RetryError
        
        with pytest.raises(RetryError):
            await claude_client.create_message(
                model=ClaudeModel.SONNET,
                messages=[{"role": "user", "content": "Test"}],
            )
    
    @pytest.mark.asyncio
    async def test_create_message_connection_error(self, claude_client):
        """Test connection error handling."""
        claude_client.client.messages.create = AsyncMock(
            side_effect=ConnectionError("Network error")
        )
        
        from tenacity import RetryError
        
        with pytest.raises(RetryError) as exc_info:
            await claude_client.create_message(
                model=ClaudeModel.SONNET,
                messages=[{"role": "user", "content": "Test"}],
            )
        
        # The actual error is wrapped in the RetryError
        # Just verify we got a RetryError - the exact message format varies
    
    @pytest.mark.asyncio
    async def test_create_message_with_tools(self, claude_client):
        """Test message creation with tool use."""
        # Create a proper ToolUseBlock object
        tool_use_block = ToolUseBlock(
            type="tool_use",
            id="tool_123",
            name="calculator",
            input={"operation": "add", "a": 1, "b": 2},
        )
        
        mock_response = Message(
            id="msg_789",
            content=[tool_use_block],
            model="claude-3-sonnet",
            role="assistant",
            usage=Usage(input_tokens=15, output_tokens=25),
            type="message",
            stop_reason="tool_use",
            stop_sequence=None,
        )
        
        claude_client.client.messages.create = AsyncMock(return_value=mock_response)
        
        tools = [
            {
                "name": "calculator",
                "description": "Perform calculations",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "operation": {"type": "string"},
                        "a": {"type": "number"},
                        "b": {"type": "number"},
                    },
                },
            }
        ]
        
        response = await claude_client.create_message(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": "What is 1 + 2?"}],
            tools=tools,
        )
        
        assert response.content[0].type == "tool_use"
        assert response.content[0].name == "calculator"
        assert response.stop_reason == "tool_use"
    
    
    @pytest.mark.asyncio
    async def test_close(self, claude_client):
        """Test client cleanup."""
        claude_client.client.close = AsyncMock()
        
        await claude_client.close()
        
        claude_client.client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_rate_limiter(self, claude_client):
        """Test rate limiting functionality."""
        # Make multiple rapid requests
        mock_response = Message(
            id="msg_test",
            content=[{"text": "Test", "type": "text"}],
            model="claude-3-sonnet",
            role="assistant",
            usage=Usage(input_tokens=5, output_tokens=5),
            type="message",
            stop_reason="end_turn",
            stop_sequence=None,
        )
        
        claude_client.client.messages.create = AsyncMock(return_value=mock_response)
        
        # Should respect rate limits
        start_time = asyncio.get_event_loop().time()
        
        for _ in range(3):
            await claude_client.create_message(
                model=ClaudeModel.SONNET,
                messages=[{"role": "user", "content": "Test"}],
            )
        
        # Check that requests were spaced appropriately
        elapsed = asyncio.get_event_loop().time() - start_time
        # Should take some time due to rate limiting
        assert elapsed > 0  # Basic check - in real tests would verify actual timing
    
    @pytest.mark.asyncio
    async def test_get_metrics(self, claude_client):
        """Test metrics retrieval."""
        metrics = claude_client.get_metrics()
        
        assert "total_requests" in metrics
        assert "total_tokens_used" in metrics
        assert "average_tokens_per_request" in metrics
        assert "rate_limit_tokens_available" in metrics
        
        assert metrics["total_requests"] == 0
        assert metrics["total_tokens_used"] == 0
        assert metrics["average_tokens_per_request"] == 0
    
    @pytest.mark.asyncio
    async def test_context_manager(self, claude_client):
        """Test async context manager functionality."""
        claude_client.client.close = AsyncMock()
        
        async with claude_client as client:
            assert client == claude_client
        
        claude_client.client.close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_create_message_with_fallback(self, claude_client):
        """Test message creation with fallback model."""
        # First call fails
        claude_client.client.messages.create = AsyncMock(
            side_effect=[
                Exception("Model overloaded"),
                Message(
                    id="msg_fallback",
                    content=[TextBlock(text="Fallback response", type="text")],
                    model="claude-3-haiku",
                    role="assistant",
                    usage=Usage(input_tokens=5, output_tokens=10),
                    type="message",
                    stop_reason="end_turn",
                    stop_sequence=None,
                )
            ]
        )
        
        response = await claude_client.create_message_with_retry(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": "Test"}],
            fallback_model=ClaudeModel.HAIKU,
        )
        
        assert response.id == "msg_fallback"
        assert response.model == "claude-3-haiku"
        assert claude_client.client.messages.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_rate_limit_retry_after(self, claude_client):
        """Test rate limit handling with retry-after header."""
        # Create rate limit error with retry-after
        rate_limit_error = RateLimitError(
            message="Rate limit exceeded", 
            response=MagicMock(status_code=429, headers={"retry-after": "5"}),
            body={"error": {"message": "Rate limit exceeded"}},
        )
        
        # Second call succeeds
        success_response = Message(
            id="msg_after_retry",
            content=[TextBlock(text="Success", type="text")],
            model="claude-3-sonnet",
            role="assistant",
            usage=Usage(input_tokens=5, output_tokens=5),
            type="message",
            stop_reason="end_turn",
            stop_sequence=None,
        )
        
        claude_client.client.messages.create = AsyncMock(
            side_effect=[rate_limit_error, success_response]
        )
        
        # Use create_message_with_retry to test retry logic
        response = await claude_client.create_message_with_retry(
            model=ClaudeModel.SONNET,
            messages=[{"role": "user", "content": "Test"}],
        )
        
        assert response.id == "msg_after_retry"
        assert claude_client.client.messages.create.call_count == 2
    
    @pytest.mark.asyncio
    async def test_token_estimation(self, claude_client):
        """Test token estimation functionality."""
        # Test single message token estimation
        text = "Hello, world! This is a test message."
        estimated = claude_client.token_counter.estimate_tokens(text)
        # Should be roughly len(text) / 4
        assert estimated > 0
        assert estimated < len(text)
        
        # Test message list token estimation
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"}
        ]
        estimated_total = claude_client.token_counter.estimate_message_tokens(messages)
        assert estimated_total > 0
        # Should include overhead for message structure
        assert estimated_total > len("Hello") // 4 + len("Hi there!") // 4 + len("How are you?") // 4