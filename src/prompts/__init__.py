"""Prompts module for the Agentic Coding System."""

from .agent_prompts import (
    get_agent_prompt,
    create_collaboration_prompt,
    CODE_GENERATION_PROMPT,
    TEST_GENERATION_PROMPT,
    DOCUMENTATION_PROMPT,
    REFACTORING_PROMPT,
    DEBUG_ANALYSIS_PROMPT,
    AGENT_INSTRUCTION_PROMPT,
    AGENT_STATUS_PROMPT,
)
from .task_decomposition import (
    get_decomposition_prompt,
    create_custom_decomposition_prompt,
    TASK_ANALYSIS_PROMPT,
    DEPENDENCY_ANALYSIS_PROMPT,
    TASK_SPECIFICATION_PROMPT,
    COMPLEXITY_ESTIMATION_PROMPT,
    PROGRESS_AGGREGATION_PROMPT,
)

__all__ = [
    # Agent prompts
    "get_agent_prompt",
    "create_collaboration_prompt",
    "CODE_GENERATION_PROMPT",
    "TEST_GENERATION_PROMPT", 
    "DOCUMENTATION_PROMPT",
    "REFACTORING_PROMPT",
    "DEBUG_ANALYSIS_PROMPT",
    "AGENT_INSTRUCTION_PROMPT",
    "AGENT_STATUS_PROMPT",
    # Task decomposition prompts
    "get_decomposition_prompt",
    "create_custom_decomposition_prompt",
    "TASK_ANALYSIS_PROMPT",
    "DEPENDENCY_ANALYSIS_PROMPT",
    "TASK_SPECIFICATION_PROMPT",
    "COMPLEXITY_ESTIMATION_PROMPT",
    "PROGRESS_AGGREGATION_PROMPT",
]