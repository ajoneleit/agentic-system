"""Claude API client with async support and advanced features.

This module provides a robust, production-ready client for interacting with
the Anthropic Claude API, including rate limiting, retry logic, and monitoring.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

import aiohttp
import orjson
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageStreamEvent
from structlog import get_logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import ClaudeModel, get_settings
from src.core.exceptions import (
    APIError,
    APIKeyError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
)


logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, rate_limit: int, interval: timedelta = timedelta(minutes=1)):
        """Initialize rate limiter.
        
        Args:
            rate_limit: Maximum requests per interval
            interval: Time interval for rate limiting
        """
        self.rate_limit = rate_limit
        self.interval = interval
        self.tokens = rate_limit
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens, waiting if necessary.
        
        Args:
            tokens: Number of tokens to acquire
        """
        async with self._lock:
            await self._wait_for_tokens(tokens)
            self.tokens -= tokens
    
    async def _wait_for_tokens(self, tokens: int) -> None:
        """Wait until enough tokens are available.
        
        Args:
            tokens: Number of tokens needed
        """
        while True:
            self._refill()
            if self.tokens >= tokens:
                return
            sleep_time = (tokens - self.tokens) * (self.interval.total_seconds() / self.rate_limit)
            await asyncio.sleep(sleep_time)
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self.last_update
        refill_amount = elapsed * (self.rate_limit / self.interval.total_seconds())
        self.tokens = min(self.rate_limit, self.tokens + refill_amount)
        self.last_update = now


class TokenCounter:
    """Estimates token usage for requests and responses."""
    
    # Rough approximation - in production, use tiktoken or similar
    CHARS_PER_TOKEN = 4
    
    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estimate token count for text.
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Estimated token count
        """
        return len(text) // cls.CHARS_PER_TOKEN
    
    @classmethod
    def estimate_message_tokens(cls, messages: List[Dict[str, str]]) -> int:
        """Estimate tokens for a list of messages.
        
        Args:
            messages: List of message dictionaries
            
        Returns:
            Estimated total token count
        """
        total = 0
        for message in messages:
            # Add tokens for role and content
            total += cls.estimate_tokens(message.get("role", ""))
            total += cls.estimate_tokens(message.get("content", ""))
            # Add overhead for message structure
            total += 4
        return total


class ClaudeClient:
    """Production-ready Claude API client with advanced features."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """Initialize Claude client.
        
        Args:
            api_key: Anthropic API key (defaults to settings)
            base_url: API base URL (defaults to settings)
            timeout: Request timeout in seconds (defaults to settings)
            max_retries: Maximum retry attempts (defaults to settings)
        """
        settings = get_settings()
        
        # Use provided values or fall back to settings
        self.api_key = api_key or settings.api.key.get_secret_value()
        if not self.api_key:
            raise APIKeyError()
            
        self.base_url = base_url or settings.api.base_url
        self.timeout = timeout or settings.api.timeout
        self.max_retries = max_retries or settings.api.max_retries
        
        # Initialize Anthropic client
        self.client = AsyncAnthropic(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=self.timeout,
        )
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(settings.api.rate_limit_per_minute)
        
        # Token tracking
        self.token_counter = TokenCounter()
        self.total_tokens_used = 0
        self.total_requests = 0
        
        # Model limits (approximate)
        self.model_limits = {
            ClaudeModel.OPUS: 200000,
            ClaudeModel.SONNET: 200000,
            ClaudeModel.HAIKU: 200000,
        }
        
        logger.info(
            "Claude client initialized",
            base_url=self.base_url,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
    
    @retry(
        retry=retry_if_exception_type((APITimeoutError, APIResponseError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def create_message(
        self,
        model: Union[ClaudeModel, str],
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Message:
        """Create a message using Claude API.
        
        Args:
            model: Model to use
            messages: List of message dictionaries
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            system: System prompt
            metadata: Additional metadata for logging
            **kwargs: Additional parameters for the API
            
        Returns:
            Claude API response message
            
        Raises:
            APIError: Various API-related errors
        """
        # Validate model
        if isinstance(model, str):
            model = ClaudeModel(model)
            
        # Estimate tokens and check limits
        estimated_tokens = self.token_counter.estimate_message_tokens(messages)
        if system:
            estimated_tokens += self.token_counter.estimate_tokens(system)
            
        model_limit = self.model_limits.get(model, 200000)
        if estimated_tokens + max_tokens > model_limit:
            logger.warning(
                "Token limit may be exceeded",
                estimated_tokens=estimated_tokens,
                max_tokens=max_tokens,
                model_limit=model_limit,
            )
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # Prepare request
        request_data = {
            "model": model.value,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }
        
        if system:
            request_data["system"] = system
        
        # Log request
        logger.info(
            "Creating Claude message",
            model=model.value,
            message_count=len(messages),
            estimated_tokens=estimated_tokens,
            metadata=metadata,
        )
        
        try:
            start_time = time.time()
            
            # Make API request
            response = await self.client.messages.create(**request_data)
            
            # Track metrics
            elapsed_time = time.time() - start_time
            self.total_requests += 1
            self.total_tokens_used += response.usage.input_tokens + response.usage.output_tokens
            
            logger.info(
                "Claude message created successfully",
                model=model.value,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                elapsed_time=elapsed_time,
                metadata=metadata,
            )
            
            return response
            
        except asyncio.TimeoutError as e:
            logger.error("API request timed out", model=model.value, timeout=self.timeout)
            raise APITimeoutError(self.timeout, "create_message") from e
            
        except Exception as e:
            if "rate_limit" in str(e).lower():
                # Extract retry-after if available
                retry_after = None
                if hasattr(e, "response") and e.response:
                    retry_after = e.response.headers.get("retry-after")
                    if retry_after:
                        retry_after = int(retry_after)
                        
                logger.warning(
                    "Rate limit exceeded",
                    retry_after=retry_after,
                    total_requests=self.total_requests,
                )
                raise APIRateLimitError(retry_after=retry_after) from e
                
            elif "api_key" in str(e).lower() or "authentication" in str(e).lower():
                logger.error("API key error")
                raise APIKeyError() from e
                
            else:
                logger.error(
                    "API request failed",
                    error=str(e),
                    model=model.value,
                )
                raise APIResponseError(reason=str(e)) from e
    
    @asynccontextmanager
    async def stream_message(
        self,
        model: Union[ClaudeModel, str],
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        temperature: float = 0.7,
        system: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[MessageStreamEvent, None]:
        """Stream a message response from Claude API.
        
        Args:
            model: Model to use
            messages: List of message dictionaries
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            system: System prompt
            metadata: Additional metadata for logging
            **kwargs: Additional parameters for the API
            
        Yields:
            Stream events from the API
            
        Raises:
            APIError: Various API-related errors
        """
        # Validate model
        if isinstance(model, str):
            model = ClaudeModel(model)
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        # Prepare request
        request_data = {
            "model": model.value,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        
        if system:
            request_data["system"] = system
        
        logger.info(
            "Starting Claude message stream",
            model=model.value,
            message_count=len(messages),
            metadata=metadata,
        )
        
        try:
            start_time = time.time()
            total_tokens = 0
            
            async with self.client.messages.stream(**request_data) as stream:
                async for event in stream:
                    yield event
                    
                    # Track tokens from events
                    if hasattr(event, "usage"):
                        total_tokens = event.usage.total_tokens
            
            # Track metrics
            elapsed_time = time.time() - start_time
            self.total_requests += 1
            self.total_tokens_used += total_tokens
            
            logger.info(
                "Claude stream completed",
                model=model.value,
                total_tokens=total_tokens,
                elapsed_time=elapsed_time,
                metadata=metadata,
            )
            
        except asyncio.TimeoutError as e:
            logger.error("Stream timed out", model=model.value, timeout=self.timeout)
            raise APITimeoutError(self.timeout, "stream_message") from e
            
        except Exception as e:
            logger.error(
                "Stream failed",
                error=str(e),
                model=model.value,
            )
            raise APIResponseError(reason=str(e)) from e
    
    async def create_message_with_retry(
        self,
        model: Union[ClaudeModel, str],
        messages: List[Dict[str, str]],
        max_retries: Optional[int] = None,
        fallback_model: Optional[ClaudeModel] = None,
        **kwargs: Any,
    ) -> Message:
        """Create message with automatic retry and fallback.
        
        Args:
            model: Primary model to use
            messages: List of message dictionaries
            max_retries: Override default max retries
            fallback_model: Model to use if primary fails
            **kwargs: Additional parameters for create_message
            
        Returns:
            Claude API response message
        """
        max_retries = max_retries or self.max_retries
        
        # Try primary model
        for attempt in range(max_retries):
            try:
                return await self.create_message(model, messages, **kwargs)
            except APIRateLimitError as e:
                if e.retry_after and attempt < max_retries - 1:
                    logger.info(
                        f"Rate limited, waiting {e.retry_after}s before retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                    )
                    await asyncio.sleep(e.retry_after)
                    continue
                raise
            except APIError as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(
                        f"Request failed, retrying in {wait_time}s",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        error=str(e),
                    )
                    await asyncio.sleep(wait_time)
                    continue
                    
                # Try fallback model if available
                if fallback_model and fallback_model != model:
                    logger.info(
                        "Trying fallback model",
                        primary_model=model,
                        fallback_model=fallback_model,
                    )
                    return await self.create_message(fallback_model, messages, **kwargs)
                    
                raise
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get client metrics.
        
        Returns:
            Dictionary of metrics
        """
        return {
            "total_requests": self.total_requests,
            "total_tokens_used": self.total_tokens_used,
            "average_tokens_per_request": (
                self.total_tokens_used / self.total_requests
                if self.total_requests > 0
                else 0
            ),
            "rate_limit_tokens_available": self.rate_limiter.tokens,
        }
    
    async def close(self) -> None:
        """Close the client and clean up resources."""
        await self.client.close()
        logger.info("Claude client closed")
    
    async def __aenter__(self) -> "ClaudeClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        await self.close()


async def create_claude_client(**kwargs: Any) -> ClaudeClient:
    """Factory function to create a Claude client.
    
    Args:
        **kwargs: Arguments to pass to ClaudeClient
        
    Returns:
        Configured Claude client instance
    """
    return ClaudeClient(**kwargs)