"""OpenAI client implementation for the Agentic Coding System.

This module provides a client that interfaces with OpenAI's API, supporting
models like GPT-4, and ready for future models like o3.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta

import aiohttp
from openai import AsyncOpenAI
from structlog import get_logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import get_settings
from src.core.exceptions import (
    APIError,
    APIKeyError,
    APIRateLimitError,
    APIResponseError,
    APITimeoutError,
)


logger = get_logger(__name__)


class OpenAIModel:
    """Available OpenAI model variants."""
    # Current models
    GPT4_TURBO = "gpt-4-turbo-preview"
    GPT4 = "gpt-4"
    GPT4_32K = "gpt-4-32k"
    GPT35_TURBO = "gpt-3.5-turbo"
    GPT35_TURBO_16K = "gpt-3.5-turbo-16k"
    
    # O1 models
    O1 = "o1"
    O1_MINI = "o1-mini"
    O1_PREVIEW = "o1-preview"
    O1_PRO = "o1-pro"
    
    # O3 models
    O3 = "o3"  # OpenAI's o3 model
    O3_MINI = "o3-mini"  # O3 mini version
    O3_PRO = "o3-pro"  # O3 pro version
    O3_DEEP_RESEARCH = "o3-deep-research"  # O3 deep research model


class OpenAIClient:
    """Client for interacting with OpenAI's API.
    
    This client provides a similar interface to ClaudeClient but uses
    OpenAI's models instead.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = OpenAIModel.GPT4_TURBO,
        max_retries: int = 3,
        timeout: int = 300,
    ):
        """Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key (defaults to settings)
            model: Default model to use
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
        """
        settings = get_settings()
        
        # Get API key from settings or parameter
        self.api_key = api_key or settings.openai.key.get_secret_value() if hasattr(settings, 'openai') else None
        if not self.api_key:
            # Fall back to environment variable
            import os
            self.api_key = os.getenv('OPENAI_API_KEY')
            
        if not self.api_key:
            raise APIKeyError("OpenAI API key is required")
            
        # Use the configured model or default
        if hasattr(settings, 'openai') and hasattr(settings.openai, 'meta_agent_model'):
            self.model = settings.openai.meta_agent_model
        else:
            self.model = model
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Initialize OpenAI client
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            timeout=self.timeout,
        )
        
        # Token tracking
        self.total_tokens_used = 0
        self.total_requests = 0
        
        logger.info(
            "OpenAI client initialized",
            model=self.model,
            timeout=self.timeout,
            max_retries=self.max_retries,
        )
    
    @retry(
        retry=retry_if_exception_type((APITimeoutError, APIRateLimitError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    async def create_message(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> Dict[str, Any]:
        """Create a chat completion using OpenAI's API.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (defaults to instance model)
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature
            **kwargs: Additional parameters for the API
            
        Returns:
            Response dictionary with generated content
        """
        model = model or self.model
        
        # Log the request
        logger.info(
            "Creating OpenAI message",
            model=model,
            message_count=len(messages),
            max_tokens=max_tokens,
        )
        
        try:
            # List of newer models with special requirements
            newer_models = ["o3", "o3-mini", "o3-pro", "o3-deep-research", "o1", "o1-mini", "o1-preview", "o1-pro"]
            
            # Prepare request parameters
            request_params = {
                "model": model,
                "messages": messages,
                **kwargs,
            }
            
            # Handle temperature - newer models only support temperature=1
            if model in newer_models:
                # o3 and o1 models only support temperature=1
                request_params["temperature"] = 1
            else:
                request_params["temperature"] = temperature
            
            # Handle max tokens parameter - newer models use max_completion_tokens
            if max_tokens:
                if model in newer_models:
                    request_params["max_completion_tokens"] = max_tokens
                else:
                    request_params["max_tokens"] = max_tokens
            
            # Make the API call
            response = await self.client.chat.completions.create(**request_params)
            
            # Track usage
            self.total_requests += 1
            if response.usage:
                self.total_tokens_used += response.usage.total_tokens
            
            # Extract the response content
            content = response.choices[0].message.content
            
            # Format response similar to Claude client
            return {
                "content": content,
                "model": model,
                "usage": {
                    "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "output_tokens": response.usage.completion_tokens if response.usage else 0,
                },
                "stop_reason": response.choices[0].finish_reason,
            }
            
        except Exception as e:
            if "invalid_api_key" in str(e) or "Incorrect API key" in str(e):
                logger.error("API key error")
                raise APIKeyError("OpenAI API key is invalid") from e
            elif "rate_limit" in str(e):
                logger.warning("Rate limit hit, will retry")
                raise APIRateLimitError("OpenAI rate limit exceeded") from e
            elif "timeout" in str(e):
                logger.warning("Request timeout")
                raise APITimeoutError("OpenAI request timed out") from e
            else:
                logger.error(f"OpenAI API error: {e}")
                raise APIResponseError(f"OpenAI API error: {str(e)}") from e
    
    async def create_message_for_task_decomposition(
        self,
        user_request: str,
        **kwargs,
    ) -> str:
        """Create a message specifically for task decomposition.
        
        This method formats the request for OpenAI to decompose a user request
        into subtasks, similar to how the Claude client works.
        
        Args:
            user_request: The user's request to decompose
            **kwargs: Additional parameters
            
        Returns:
            JSON string with decomposed tasks
        """
        # Use a system message to set up the task decomposition role
        messages = [
            {
                "role": "system",
                "content": """You are a Meta Agent responsible for decomposing user requests into subtasks.
                
Your response must be a valid JSON object with this structure:
{
    "project_name": "short_descriptive_name",
    "tasks": [
        {
            "id": "unique_id",
            "name": "Task name",
            "description": "Detailed description",
            "type": "core_logic|testing|documentation|optimization",
            "dependencies": ["task_id1", "task_id2"],
            "priority": "high|medium|low",
            "estimated_complexity": "simple|moderate|complex"
        }
    ]
}

Guidelines:
- Break down the request into logical, atomic subtasks
- Include tasks for implementation, testing, documentation
- Set appropriate dependencies between tasks
- Use descriptive but concise task names"""
            },
            {
                "role": "user",
                "content": f"Please decompose this request into subtasks: {user_request}"
            }
        ]
        
        # Get response with higher max tokens for complex decompositions
        # Remove temperature from kwargs if present to avoid conflict
        kwargs.pop('temperature', None)
        response = await self.create_message(
            messages=messages,
            max_tokens=2000,
            temperature=0.3,  # Lower temperature for more consistent JSON
            **kwargs,
        )
        
        return response["content"]
    
    async def create_message_for_code_generation(
        self,
        task_description: str,
        context: Optional[str] = None,
        **kwargs,
    ) -> str:
        """Create a message for code generation tasks.
        
        Args:
            task_description: Description of the code to generate
            context: Additional context or requirements
            **kwargs: Additional parameters
            
        Returns:
            Generated code as a string
        """
        messages = [
            {
                "role": "system",
                "content": "You are an expert programmer. Generate high-quality, well-documented code based on the requirements. Include error handling and follow best practices."
            },
            {
                "role": "user",
                "content": task_description
            }
        ]
        
        if context:
            messages.append({
                "role": "assistant",
                "content": "I understand. Let me review the context."
            })
            messages.append({
                "role": "user",
                "content": context
            })
        
        response = await self.create_message(
            messages=messages,
            max_tokens=3000,
            temperature=0.5,
            **kwargs,
        )
        
        return response["content"]
    
    async def close(self):
        """Close the client and cleanup resources."""
        logger.info("OpenAI client closed")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get usage statistics for the client.
        
        Returns:
            Dictionary with usage stats
        """
        return {
            "total_requests": self.total_requests,
            "total_tokens_used": self.total_tokens_used,
            "average_tokens_per_request": (
                self.total_tokens_used / self.total_requests
                if self.total_requests > 0
                else 0
            ),
        }