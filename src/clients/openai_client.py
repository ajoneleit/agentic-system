"""
OpenAI Client for o3 model integration.

This module provides a client for interacting with OpenAI's o3 models,
specifically designed for prompt evolution and autonomous refinement tasks.
"""

import asyncio
import logging
from enum import Enum
from typing import Any, Dict, List, Optional

import openai
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class OpenAIModel(Enum):
    """Enumeration of supported OpenAI models."""
    
    O3_MINI = "o3-mini"
    O3 = "o3"
    GPT_4O = "gpt-4o"
    GPT_4O_MINI = "gpt-4o-mini"


class OpenAIClient:
    """
    Client for interacting with OpenAI's API, optimized for prompt evolution tasks.
    
    This client provides methods for:
    - Creating messages with o3 models
    - Managing conversations
    - Handling rate limiting and errors
    - Monitoring usage and costs
    """
    
    def __init__(self, api_key: str, config: Dict[str, Any] = None):
        """Initialize the OpenAI client.
        
        Args:
            api_key: OpenAI API key
            config: Optional configuration parameters
        """
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
        # Initialize OpenAI client
        self.client = AsyncOpenAI(api_key=api_key)
        
        # Configuration
        self.default_model = OpenAIModel.O3_MINI
        self.max_tokens = self.config.get("max_tokens", 2000)
        self.temperature = self.config.get("temperature", 0.7)
        self.timeout = self.config.get("timeout", 30)
        
        # Rate limiting
        self.rate_limit_delay = self.config.get("rate_limit_delay", 1.0)
        self.max_retries = self.config.get("max_retries", 3)
        
        # Usage tracking
        self.usage_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "failed_requests": 0,
            "model_usage": {}
        }
    
    async def create_message(self, 
                           messages: List[Dict[str, str]], 
                           model: OpenAIModel = None,
                           max_tokens: int = None,
                           temperature: float = None,
                           **kwargs) -> Dict[str, Any]:
        """
        Create a message using the specified model.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (defaults to configured default)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            **kwargs: Additional parameters
            
        Returns:
            Dictionary with response content and metadata
        """
        # Use defaults if not specified
        model = model or self.default_model
        max_tokens = max_tokens or self.max_tokens
        temperature = temperature if temperature is not None else self.temperature
        
        retry_count = 0
        last_error = None
        
        while retry_count < self.max_retries:
            try:
                self.logger.debug(f"Creating message with model {model.value}")
                
                # Make the API call
                response = await self.client.chat.completions.create(
                    model=model.value,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=self.timeout,
                    **kwargs
                )
                
                # Extract response data
                content = response.choices[0].message.content
                usage = response.usage
                
                # Update usage statistics
                self._update_usage_stats(model, usage)
                
                return {
                    "content": content,
                    "model": model.value,
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens
                    },
                    "finish_reason": response.choices[0].finish_reason
                }
                
            except openai.RateLimitError as e:
                retry_count += 1
                last_error = e
                delay = self.rate_limit_delay * (2 ** retry_count)  # Exponential backoff
                self.logger.warning(f"Rate limit hit, retrying in {delay}s (attempt {retry_count})")
                await asyncio.sleep(delay)
                
            except openai.APITimeoutError as e:
                retry_count += 1
                last_error = e
                self.logger.warning(f"API timeout, retrying (attempt {retry_count})")
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error creating message: {str(e)}")
                self.usage_stats["failed_requests"] += 1
                raise e
        
        # If we've exhausted retries
        self.usage_stats["failed_requests"] += 1
        raise last_error or Exception("Max retries exceeded")
    
    async def create_evolution_prompt(self, 
                                    original_prompt: str,
                                    strategy: str,
                                    metrics: Dict[str, Any],
                                    context: Dict[str, Any] = None) -> Optional[str]:
        """
        Create an evolved prompt using specialized prompt engineering.
        
        Args:
            original_prompt: The original prompt to improve
            strategy: Evolution strategy to apply
            metrics: Performance metrics for the original prompt
            context: Additional context for evolution
            
        Returns:
            Evolved prompt or None if evolution failed
        """
        try:
            # Build evolution context
            context = context or {}
            success_rate = metrics.get("success_rate", 0.0)
            avg_time = metrics.get("avg_execution_time", 0.0)
            error_patterns = metrics.get("error_patterns", [])
            
            evolution_prompt = f"""
You are an expert prompt engineer specializing in autonomous prompt improvement. Your task is to evolve the following prompt using the "{strategy}" strategy.

ORIGINAL PROMPT:
{original_prompt}

PERFORMANCE METRICS:
- Success Rate: {success_rate:.2f} ({success_rate*100:.1f}%)
- Average Execution Time: {avg_time:.2f}s
- Common Error Patterns: {', '.join(error_patterns[:3]) if error_patterns else 'None'}

EVOLUTION STRATEGY: {strategy}

REQUIREMENTS:
1. Maintain the core intent and functionality of the original prompt
2. Address the performance issues identified in the metrics
3. Apply the specific evolution strategy focus
4. Ensure the evolved prompt is clear, specific, and actionable
5. Optimize for better success rates and reduced execution time

EVOLUTION FOCUS AREAS:
- If strategy is "clarity_enhancement": Improve clarity, specificity, and reduce ambiguity
- If strategy is "context_optimization": Better context setting and example provision
- If strategy is "structure_refinement": Improve logical flow and organization
- If strategy is "performance_tuning": Optimize for speed and efficiency

Please provide ONLY the improved prompt without any explanatory text or commentary.
"""
            
            messages = [{"role": "user", "content": evolution_prompt}]
            
            response = await self.create_message(
                messages=messages,
                model=OpenAIModel.O3_MINI,
                temperature=0.3,  # Lower temperature for more focused evolution
                max_tokens=2000
            )
            
            return response["content"].strip()
            
        except Exception as e:
            self.logger.error(f"Error creating evolution prompt: {str(e)}")
            return None
    
    async def analyze_prompt_quality(self, prompt: str) -> Dict[str, Any]:
        """
        Analyze the quality of a prompt and provide improvement suggestions.
        
        Args:
            prompt: Prompt to analyze
            
        Returns:
            Quality analysis results
        """
        try:
            analysis_prompt = f"""
Analyze the following prompt for quality and effectiveness. Provide a structured assessment.

PROMPT TO ANALYZE:
{prompt}

Please provide your analysis in the following JSON format:
{{
    "clarity_score": 0.0-1.0,
    "specificity_score": 0.0-1.0,
    "structure_score": 0.0-1.0,
    "completeness_score": 0.0-1.0,
    "overall_score": 0.0-1.0,
    "strengths": ["list", "of", "strengths"],
    "weaknesses": ["list", "of", "weaknesses"],
    "improvement_suggestions": ["list", "of", "suggestions"]
}}
"""
            
            messages = [{"role": "user", "content": analysis_prompt}]
            
            response = await self.create_message(
                messages=messages,
                model=OpenAIModel.O3_MINI,
                temperature=0.1,  # Very low temperature for consistent analysis
                max_tokens=1000
            )
            
            # Try to parse as JSON
            import json
            try:
                return json.loads(response["content"])
            except json.JSONDecodeError:
                # Fallback to text response
                return {"analysis": response["content"], "error": "Failed to parse JSON"}
                
        except Exception as e:
            self.logger.error(f"Error analyzing prompt quality: {str(e)}")
            return {"error": str(e)}
    
    async def generate_template_variations(self, 
                                         base_template: str, 
                                         num_variations: int = 3) -> List[str]:
        """
        Generate variations of a base template for A/B testing.
        
        Args:
            base_template: Base template to create variations from
            num_variations: Number of variations to generate
            
        Returns:
            List of template variations
        """
        try:
            variation_prompt = f"""
Create {num_variations} different variations of the following prompt template. Each variation should:
1. Maintain the core functionality and intent
2. Use different wording, structure, or approach
3. Be suitable for A/B testing
4. Include the same variable placeholders

BASE TEMPLATE:
{base_template}

Please provide exactly {num_variations} variations, each on a separate line starting with "VARIATION N:"
"""
            
            messages = [{"role": "user", "content": variation_prompt}]
            
            response = await self.create_message(
                messages=messages,
                model=OpenAIModel.O3_MINI,
                temperature=0.8,  # Higher temperature for more diverse variations
                max_tokens=2000
            )
            
            # Parse variations from response
            variations = []
            lines = response["content"].split('\n')
            
            for line in lines:
                if line.strip().startswith("VARIATION"):
                    # Extract content after "VARIATION N:"
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        variations.append(parts[1].strip())
            
            return variations[:num_variations]  # Ensure we don't return more than requested
            
        except Exception as e:
            self.logger.error(f"Error generating template variations: {str(e)}")
            return []
    
    def get_usage_stats(self) -> Dict[str, Any]:
        """Get current usage statistics.
        
        Returns:
            Dictionary with usage statistics
        """
        return self.usage_stats.copy()
    
    def reset_usage_stats(self):
        """Reset usage statistics."""
        self.usage_stats = {
            "total_requests": 0,
            "total_tokens": 0,
            "total_cost": 0.0,
            "failed_requests": 0,
            "model_usage": {}
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform a health check on the OpenAI API connection.
        
        Returns:
            Health check results
        """
        try:
            # Simple test message
            test_messages = [{"role": "user", "content": "Hello, this is a health check test."}]
            
            response = await self.create_message(
                messages=test_messages,
                max_tokens=10,
                temperature=0.1
            )
            
            return {
                "status": "healthy",
                "model": response["model"],
                "response_time": "< 1s",  # Simplified for now
                "test_successful": True
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "test_successful": False
            }
    
    # Private helper methods
    
    def _update_usage_stats(self, model: OpenAIModel, usage):
        """Update usage statistics after API call."""
        self.usage_stats["total_requests"] += 1
        self.usage_stats["total_tokens"] += usage.total_tokens
        
        # Update model-specific usage
        model_name = model.value
        if model_name not in self.usage_stats["model_usage"]:
            self.usage_stats["model_usage"][model_name] = {
                "requests": 0,
                "tokens": 0,
                "cost": 0.0
            }
        
        self.usage_stats["model_usage"][model_name]["requests"] += 1
        self.usage_stats["model_usage"][model_name]["tokens"] += usage.total_tokens
        
        # Estimate cost (simplified pricing model)
        cost = self._estimate_cost(model, usage)
        self.usage_stats["total_cost"] += cost
        self.usage_stats["model_usage"][model_name]["cost"] += cost
    
    def _estimate_cost(self, model: OpenAIModel, usage) -> float:
        """Estimate cost for API usage (simplified pricing)."""
        # Simplified pricing model - replace with actual OpenAI pricing
        pricing = {
            OpenAIModel.O3_MINI: {"input": 0.00015, "output": 0.0006},  # per 1K tokens
            OpenAIModel.O3: {"input": 0.003, "output": 0.012},
            OpenAIModel.GPT_4O: {"input": 0.0025, "output": 0.01},
            OpenAIModel.GPT_4O_MINI: {"input": 0.00015, "output": 0.0006}
        }
        
        if model not in pricing:
            return 0.0
        
        input_cost = (usage.prompt_tokens / 1000) * pricing[model]["input"]
        output_cost = (usage.completion_tokens / 1000) * pricing[model]["output"]
        
        return input_cost + output_cost


class OpenAIClientFactory:
    """Factory for creating OpenAI clients with different configurations."""
    
    @staticmethod
    def create_evolution_client(api_key: str) -> OpenAIClient:
        """Create client optimized for prompt evolution tasks."""
        config = {
            "max_tokens": 2000,
            "temperature": 0.3,
            "rate_limit_delay": 1.0,
            "max_retries": 3,
            "timeout": 30
        }
        return OpenAIClient(api_key, config)
    
    @staticmethod
    def create_analysis_client(api_key: str) -> OpenAIClient:
        """Create client optimized for analysis tasks."""
        config = {
            "max_tokens": 1000,
            "temperature": 0.1,
            "rate_limit_delay": 0.5,
            "max_retries": 2,
            "timeout": 20
        }
        return OpenAIClient(api_key, config)
    
    @staticmethod
    def create_generation_client(api_key: str) -> OpenAIClient:  
        """Create client optimized for content generation."""
        config = {
            "max_tokens": 3000,
            "temperature": 0.8,
            "rate_limit_delay": 1.5,
            "max_retries": 3,
            "timeout": 45
        }
        return OpenAIClient(api_key, config)