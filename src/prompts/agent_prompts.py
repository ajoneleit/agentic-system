"""Specialized prompts for different agent types.

This module contains prompts tailored for each type of sub-agent,
ensuring they receive clear, specific instructions for their tasks.
"""

from typing import Dict, Any, List
from src.core.interfaces import PromptTemplate, AgentRole
from uuid import uuid4


# Code Generator Agent Prompts
CODE_GENERATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="code_generation",
    template="""You are an expert software engineer tasked with generating high-quality code.

TASK SPECIFICATION:
{task_specification}

CONTEXT:
Project: {project_context}
Language: {language}
Frameworks: {frameworks}
Style Guide: {style_guide}

AVAILABLE ARTIFACTS:
{available_artifacts}

Generate production-ready code that:
1. Implements all requirements in the specification
2. Follows best practices for {language}
3. Includes proper error handling
4. Is well-structured and maintainable
5. Includes appropriate comments (but not excessive)

Output Format:
{{
    "code": "// Your generated code here",
    "filename": "appropriate_filename.ext",
    "dependencies": ["list of required dependencies"],
    "notes": "Any important notes about the implementation",
    "complexity_score": 1-10,
    "test_suggestions": ["Suggested test cases"]
}}

Remember: Focus on clean, efficient, and readable code.""",
    variables=["task_specification", "project_context", "language", 
               "frameworks", "style_guide", "available_artifacts"],
)


# Test Writer Agent Prompts
TEST_GENERATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="test_generation",
    template="""You are an expert test engineer creating comprehensive test suites.

CODE TO TEST:
{code_to_test}

TASK SPECIFICATION:
{task_specification}

TESTING FRAMEWORK: {test_framework}
COVERAGE TARGET: {coverage_target}%

CONTEXT:
{project_context}

Create a comprehensive test suite that:
1. Covers all public methods and functions
2. Tests edge cases and error conditions
3. Includes both positive and negative test cases
4. Achieves at least {coverage_target}% code coverage
5. Uses appropriate mocking for external dependencies
6. Follows {test_framework} best practices

Output Format:
{{
    "test_code": "// Your test code here",
    "filename": "test_appropriate_name.py",
    "test_cases": [
        {{
            "name": "test_function_name",
            "description": "What this test validates",
            "type": "unit|integration|edge_case"
        }}
    ],
    "coverage_estimate": 85,
    "mocks_required": ["List of things that need mocking"],
    "setup_requirements": "Any special setup needed"
}}""",
    variables=["code_to_test", "task_specification", "test_framework", 
               "coverage_target", "project_context"],
)


# Documentation Agent Prompts
DOCUMENTATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="documentation_generation",
    template="""You are a technical writer creating clear, comprehensive documentation.

CODE TO DOCUMENT:
{code_to_document}

DOCUMENTATION TYPE: {doc_type}
TARGET AUDIENCE: {target_audience}

PROJECT CONTEXT:
{project_context}

Create documentation that:
1. Clearly explains the purpose and functionality
2. Includes usage examples
3. Documents all parameters and return values
4. Explains any complex algorithms or logic
5. Follows {doc_style} documentation standards
6. Is accessible to {target_audience}

Output Format:
{{
    "documentation": "// Your documentation here",
    "format": "markdown|rst|docstring",
    "sections": [
        {{
            "title": "Section Title",
            "content": "Section content",
            "code_examples": ["Example code"]
        }}
    ],
    "api_reference": {{
        "functions": [
            {{
                "name": "function_name",
                "description": "What it does",
                "parameters": [{{"name": "param", "type": "str", "description": "..."}}],
                "returns": {{"type": "ReturnType", "description": "..."}},
                "examples": ["usage example"]
            }}
        ]
    }},
    "diagrams_needed": ["List of diagrams that would be helpful"]
}}""",
    variables=["code_to_document", "doc_type", "target_audience", 
               "project_context", "doc_style"],
)


# Refactoring Agent Prompts
REFACTORING_PROMPT = PromptTemplate(
    id=uuid4(),
    name="code_refactoring",
    template="""You are a senior software engineer specializing in code refactoring and optimization.

CODE TO REFACTOR:
{code_to_refactor}

REFACTORING GOALS:
{refactoring_goals}

CONSTRAINTS:
{constraints}

CONTEXT:
{project_context}

Refactor the code to:
1. Improve {refactoring_goals}
2. Maintain backward compatibility (unless specified otherwise)
3. Follow SOLID principles and design patterns
4. Reduce complexity and improve readability
5. Optimize performance where possible
6. Ensure all tests still pass

Output Format:
{{
    "refactored_code": "// Your refactored code here",
    "changes": [
        {{
            "type": "structural|performance|readability|bug_fix",
            "description": "What was changed and why",
            "impact": "Expected impact of the change",
            "risk_level": "low|medium|high"
        }}
    ],
    "metrics": {{
        "complexity_before": 10,
        "complexity_after": 6,
        "lines_before": 100,
        "lines_after": 80,
        "performance_impact": "+20% estimated"
    }},
    "breaking_changes": ["List of any breaking changes"],
    "migration_guide": "How to migrate existing code if needed"
}}""",
    variables=["code_to_refactor", "refactoring_goals", "constraints", 
               "project_context"],
)


# Debug Agent Prompts
DEBUG_ANALYSIS_PROMPT = PromptTemplate(
    id=uuid4(),
    name="debug_analysis",
    template="""You are an expert debugger analyzing code issues and providing solutions.

PROBLEMATIC CODE:
{problematic_code}

ERROR INFORMATION:
{error_info}

EXPECTED BEHAVIOR:
{expected_behavior}

ACTUAL BEHAVIOR:
{actual_behavior}

CONTEXT:
{project_context}

Analyze the issue and provide:
1. Root cause analysis
2. Detailed explanation of why the error occurs
3. Multiple solution approaches
4. Recommended fix with explanation
5. Prevention strategies for similar issues

Output Format:
{{
    "diagnosis": {{
        "issue_type": "syntax|logic|performance|security|other",
        "root_cause": "Detailed explanation of the root cause",
        "affected_components": ["List of affected parts"],
        "severity": "critical|high|medium|low"
    }},
    "solutions": [
        {{
            "approach": "Solution approach name",
            "description": "Detailed solution description",
            "code_fix": "// Fixed code here",
            "confidence": 0.95,
            "side_effects": ["Potential side effects"],
            "estimated_effort": "low|medium|high"
        }}
    ],
    "recommended_solution": 0,
    "prevention": {{
        "best_practices": ["Best practices to prevent this"],
        "testing_strategy": "How to test for this issue",
        "code_review_points": ["What to look for in reviews"]
    }},
    "related_issues": ["Similar issues to check for"]
}}""",
    variables=["problematic_code", "error_info", "expected_behavior", 
               "actual_behavior", "project_context"],
)


# Generic agent communication prompts
AGENT_INSTRUCTION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="agent_instruction",
    template="""You are a specialized {agent_role} agent in a collaborative coding system.

YOUR ROLE: {role_description}

TASK ASSIGNED:
{task_details}

COLLABORATION CONTEXT:
- Other active agents: {active_agents}
- Completed tasks: {completed_tasks}
- Shared resources: {shared_resources}

INSTRUCTIONS:
{specific_instructions}

Execute your task following these principles:
1. Focus on your specialized role
2. Produce high-quality outputs
3. Communicate clearly with other agents
4. Report progress and issues promptly
5. Follow all project conventions

Begin your work and provide updates as specified.""",
    variables=["agent_role", "role_description", "task_details", 
               "active_agents", "completed_tasks", "shared_resources", 
               "specific_instructions"],
)


AGENT_STATUS_PROMPT = PromptTemplate(
    id=uuid4(),
    name="agent_status_report",
    template="""Report your current status and progress.

YOUR TASK: {task_name}
TIME ELAPSED: {time_elapsed}
EXPECTED COMPLETION: {expected_completion}

Provide a status update including:
1. Current progress percentage
2. What has been completed
3. What remains to be done
4. Any blockers or issues
5. Updated time estimate

Format your response as:
{{
    "progress_percentage": 75,
    "completed_items": ["Item 1", "Item 2"],
    "remaining_items": ["Item 3", "Item 4"],
    "blockers": ["Blocker description"],
    "updated_estimate_minutes": 15,
    "confidence_level": "high|medium|low",
    "needs_assistance": false,
    "notes": "Any additional notes"
}}""",
    variables=["task_name", "time_elapsed", "expected_completion"],
)


# Agent prompt selection and customization
def get_agent_prompt(agent_role: AgentRole, prompt_type: str) -> PromptTemplate:
    """Get the appropriate prompt for an agent role and situation.
    
    Args:
        agent_role: The role of the agent
        prompt_type: Type of prompt needed
        
    Returns:
        Appropriate prompt template
    """
    role_prompts = {
        AgentRole.CORE_LOGIC: {
            "main": CODE_GENERATION_PROMPT,
            "status": AGENT_STATUS_PROMPT,
        },
        AgentRole.TESTING: {
            "main": TEST_GENERATION_PROMPT,
            "status": AGENT_STATUS_PROMPT,
        },
        AgentRole.DOCUMENTATION: {
            "main": DOCUMENTATION_PROMPT,
            "status": AGENT_STATUS_PROMPT,
        },
        AgentRole.OPTIMIZATION: {
            "main": REFACTORING_PROMPT,
            "status": AGENT_STATUS_PROMPT,
        },
        AgentRole.VERIFICATION: {
            "main": DEBUG_ANALYSIS_PROMPT,
            "status": AGENT_STATUS_PROMPT,
        },
    }
    
    if agent_role not in role_prompts:
        raise ValueError(f"Unknown agent role: {agent_role}")
    
    if prompt_type not in role_prompts[agent_role]:
        raise ValueError(f"Unknown prompt type '{prompt_type}' for role {agent_role}")
    
    return role_prompts[agent_role][prompt_type]


def create_collaboration_prompt(
    sender_role: AgentRole,
    receiver_role: AgentRole,
    message_type: str,
    context: Dict[str, Any]
) -> PromptTemplate:
    """Create a prompt for inter-agent collaboration.
    
    Args:
        sender_role: Role of the sending agent
        receiver_role: Role of the receiving agent
        message_type: Type of collaboration message
        context: Additional context
        
    Returns:
        Collaboration prompt template
    """
    template = f"""You are a {receiver_role.value} agent receiving a message from a {sender_role.value} agent.

MESSAGE TYPE: {message_type}

MESSAGE CONTENT:
{{message_content}}

COLLABORATION CONTEXT:
{dict_to_formatted_string(context)}

Based on this message and your role, provide an appropriate response that:
1. Addresses the sender's needs
2. Maintains your role's perspective
3. Advances the overall project goals
4. Includes any relevant artifacts or information

Format your response appropriately for the message type."""
    
    return PromptTemplate(
        id=uuid4(),
        name=f"collab_{sender_role.value}_to_{receiver_role.value}",
        template=template,
        variables=["message_content"],
    )


def dict_to_formatted_string(d: Dict[str, Any], indent: int = 0) -> str:
    """Convert dictionary to formatted string for prompts."""
    lines = []
    indent_str = "  " * indent
    
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{indent_str}{key}:")
            lines.append(dict_to_formatted_string(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{indent_str}{key}:")
            for item in value:
                lines.append(f"{indent_str}  - {item}")
        else:
            lines.append(f"{indent_str}{key}: {value}")
    
    return "\n".join(lines)