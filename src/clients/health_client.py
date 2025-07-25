"""Health check client wrapper for Claude API connectivity testing.

This module provides a minimal client interface for health checks that wraps
the robust Claude CLI client with the API interface needed for system validation.
"""

from typing import Any

from anthropic.types import Message

from config import ClaudeModel

from .claude_cli_client_robust import ClaudeCodeClient


class HealthCheckClient:
    """Minimal Claude client wrapper for health checks."""

    def __init__(self):
        """Initialize health check client."""
        self._cli_client = ClaudeCodeClient()

    async def create_message(
        self,
        model: ClaudeModel,
        messages: list[dict[str, str]],
        max_tokens: int = 10,
        temperature: float = 0.0,
        **kwargs: Any,
    ) -> Message:
        """Create a message for health check purposes.

        Args:
            model: Model to use for health check
            messages: List of message dictionaries
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters

        Returns:
            Mock Message object with health check results

        """
        # Use the health check method from the robust client
        result = await self._cli_client.health_check()

        # Create a mock Message object that matches the expected interface
        class MockMessage:
            def __init__(self, health_result: dict):
                self.model = model.value
                self.content = [{"type": "text", "text": health_result.get("message", "")}]
                self.usage = MockUsage(health_result.get("tokens_used", 0))

        class MockUsage:
            def __init__(self, total_tokens: int):
                self.input_tokens = total_tokens // 2
                self.output_tokens = total_tokens - self.input_tokens

        if result["status"] == "ok":
            return MockMessage(result)
        else:
            # Raise appropriate exception for health check failures
            from src.core.exceptions import APIError

            raise APIError(result["message"])

    async def close(self) -> None:
        """Close the client and clean up resources."""
        await self._cli_client.close()

    async def __aenter__(self) -> "HealthCheckClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()


# Backward compatibility alias
ClaudeClient = HealthCheckClient
