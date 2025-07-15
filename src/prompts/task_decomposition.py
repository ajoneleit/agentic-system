"""Task decomposition prompts for the Meta Agent.

This module contains sophisticated prompts for analyzing user requests
and breaking them down into executable tasks with dependencies.
"""

from typing import Dict, Any
from src.core.interfaces import PromptTemplate
from uuid import uuid4


# Task decomposition prompt templates
TASK_ANALYSIS_PROMPT = PromptTemplate(
    id=uuid4(),
    name="task_analysis",
    template="""You are an expert software architect analyzing a user's coding request.

USER REQUEST:
{user_request}

Analyze this request and break it down into discrete, executable tasks. THE OUTPUT MUST BE IN THE JSON FORMAT SPECIFIED BELOW. For each task:

1. Identify the specific deliverable or outcome
2. Determine dependencies on other tasks - CRITICAL: Testing tasks MUST depend on core_logic tasks that create the code to test. Documentation tasks MUST depend on the tasks that create what they document.
3. Estimate complexity (simple/medium/complex)
4. Identify the most suitable agent type (core_logic/testing/documentation/optimization)
5. Specify any special requirements or constraints

DEPENDENCY RULES:
- Testing tasks CANNOT run before core_logic tasks that create the code
- Documentation tasks CANNOT run before the tasks they document
- Optimization tasks CANNOT run before the code exists
- CRITICAL: In the "dependencies" array, you MUST use the EXACT task name as it appears in another task's "name" field
- DO NOT use shortened names, aliases, or different variations - copy the exact name string

Output your analysis as a JSON object ONLY (no additional text before or after):
{{
    "project_summary": "Brief description of the overall project",
    "tasks": [
        {{
            "name": "Task name",
            "description": "Detailed task description",
            "deliverable": "What will be produced",
            "dependencies": ["EXACT names of tasks this depends on - must match another task's 'name' field exactly"],
            "complexity": "simple|medium|complex",
            "agent_type": "core_logic|testing|documentation|optimization",
            "estimated_time_minutes": 10,
            "requirements": {{
                "language": "python|javascript|etc",
                "frameworks": ["framework1", "framework2"],
                "special_notes": "Any special considerations"
            }}
        }}
    ],
    "execution_strategy": {{
        "parallel_groups": [["task1", "task2"], ["task3"]],
        "critical_path": ["task1", "task3", "task5"],
        "estimated_total_time_minutes": 60
    }}
}}

Be thorough and ensure all tasks are atomic and clearly defined.

CRITICAL: Tasks must have proper dependencies! Testing cannot happen before implementation!

EXAMPLE for "Create a calculator with tests":
{{
    "project_summary": "A calculator application with unit tests",
    "tasks": [
        {{
            "name": "Implement calculator logic",
            "description": "Create the core calculator functions",
            "deliverable": "calculator.py with add, subtract, multiply, divide functions",
            "dependencies": [],
            "complexity": "simple",
            "agent_type": "core_logic",
            "estimated_time_minutes": 15,
            "requirements": {{"language": "python"}}
        }},
        {{
            "name": "Write calculator tests",
            "description": "Create unit tests for calculator functions",
            "deliverable": "test_calculator.py with comprehensive tests",
            "dependencies": ["Implement calculator logic"],
            "complexity": "simple",
            "agent_type": "testing",
            "estimated_time_minutes": 20,
            "requirements": {{"language": "python", "frameworks": ["pytest"]}}
        }}
    ]
}}

Another EXAMPLE for "Create hello world script with tests":
{{
    "project_summary": "A simple hello world Python script with tests",
    "tasks": [
        {{
            "name": "Create hello world script",
            "description": "Implement the main hello world Python script",
            "deliverable": "hello_world.py",
            "dependencies": [],
            "complexity": "simple",
            "agent_type": "core_logic",
            "estimated_time_minutes": 5,
            "requirements": {{"language": "python"}}
        }},
        {{
            "name": "Write tests for hello world",
            "description": "Create unit tests for the hello world script",
            "deliverable": "test_hello_world.py",
            "dependencies": ["Create hello world script"],  // EXACT name from above task
            "complexity": "simple",
            "agent_type": "testing",
            "estimated_time_minutes": 10,
            "requirements": {{"language": "python", "frameworks": ["pytest"]}}
        }},
        {{
            "name": "Document hello world script",
            "description": "Write documentation for the hello world script",
            "deliverable": "README.md",
            "dependencies": ["Create hello world script"],  // EXACT name, not "create_script" or other variation
            "complexity": "simple",
            "agent_type": "documentation",
            "estimated_time_minutes": 5,
            "requirements": {{"language": "markdown"}}
        }}
    ]
}}

IMPORTANT: Notice how dependencies use the EXACT task names. Never use shortened versions like "implement_script" when the task is named "Implement calculator logic"!""",
    variables=["user_request"],
)


DEPENDENCY_ANALYSIS_PROMPT = PromptTemplate(
    id=uuid4(),
    name="dependency_analysis",
    template="""Analyze the dependencies between these tasks to create an optimal execution order.

TASKS:
{tasks_json}

For each task, identify:
1. Direct dependencies (must complete before this task)
2. Soft dependencies (beneficial but not required)
3. Resource conflicts (tasks that shouldn't run in parallel)
4. Optimal parallelization opportunities

Return ONLY valid JSON with no additional text or explanation. Output a dependency graph in this exact format:
{{
    "dependency_graph": {{
        "task_name": {{
            "depends_on": ["task1", "task2"],
            "soft_dependencies": ["task3"],
            "conflicts_with": ["task4"],
            "can_parallel_with": ["task5"]
        }}
    }},
    "execution_phases": [
        {{"phase": 1, "tasks": ["task1", "task2"], "can_parallel": true}},
        {{"phase": 2, "tasks": ["task3"], "can_parallel": false}}
    ],
    "critical_path": ["task1", "task3", "task5"],
    "optimization_notes": "Suggestions for optimal execution"
}}""",
    variables=["tasks_json"],
)


TASK_SPECIFICATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="task_specification",
    template="""Create a detailed specification for this task that a specialized agent can execute.

TASK: {task_name}
DESCRIPTION: {task_description}
DELIVERABLE: {deliverable}
CONTEXT: {project_context}
DEPENDENCIES COMPLETED: {completed_dependencies}

Generate a comprehensive task specification including:

1. **Objective**: Clear statement of what needs to be accomplished
2. **Inputs**: What information/artifacts are available
3. **Outputs**: Exact deliverables expected
4. **Constraints**: Any limitations or requirements
5. **Success Criteria**: How to verify task completion
6. **Implementation Guidelines**: High-level approach

Format as JSON:
{{
    "task_id": "{task_id}",
    "specification": {{
        "objective": "Clear objective statement",
        "inputs": {{
            "artifacts": ["list of available artifacts"],
            "context": "Relevant context information",
            "dependencies": {{}}
        }},
        "outputs": {{
            "primary": "Main deliverable",
            "secondary": ["Additional outputs"],
            "format": "Expected format/structure"
        }},
        "constraints": {{
            "technical": ["Technical constraints"],
            "quality": ["Quality requirements"],
            "style": ["Style guidelines"]
        }},
        "success_criteria": [
            "Criterion 1",
            "Criterion 2"
        ],
        "implementation_guide": {{
            "approach": "Recommended approach",
            "steps": ["Step 1", "Step 2"],
            "considerations": ["Important considerations"]
        }}
    }}
}}""",
    variables=["task_name", "task_description", "deliverable", "project_context", 
               "completed_dependencies", "task_id"],
)


COMPLEXITY_ESTIMATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="complexity_estimation",
    template="""Estimate the complexity and resource requirements for this task.

TASK: {task_name}
DESCRIPTION: {task_description}
TECHNICAL REQUIREMENTS: {requirements}

Analyze and provide:

1. **Complexity Score** (1-10): Based on technical difficulty
2. **Time Estimate**: Realistic time in minutes
3. **Resource Requirements**: CPU, memory, API calls
4. **Risk Factors**: Potential complications
5. **Optimization Opportunities**: Ways to simplify

Output as JSON:
{{
    "complexity_analysis": {{
        "score": 7,
        "category": "complex",
        "factors": ["Factor 1", "Factor 2"],
        "technical_challenges": ["Challenge 1"]
    }},
    "resource_estimate": {{
        "time_minutes": 30,
        "api_calls_estimate": 10,
        "memory_requirement": "low|medium|high",
        "parallel_capable": true
    }},
    "risk_assessment": {{
        "level": "low|medium|high",
        "factors": ["Risk 1"],
        "mitigation": ["Mitigation strategy"]
    }},
    "optimization": {{
        "opportunities": ["Optimization 1"],
        "trade_offs": ["Trade-off 1"]
    }}
}}""",
    variables=["task_name", "task_description", "requirements"],
)


PROGRESS_AGGREGATION_PROMPT = PromptTemplate(
    id=uuid4(),
    name="progress_aggregation",
    template="""Aggregate the progress from multiple sub-agents into a coherent status report.

ACTIVE TASKS:
{active_tasks_json}

COMPLETED TASKS:
{completed_tasks_json}

FAILED TASKS:
{failed_tasks_json}

OVERALL PROJECT:
{project_summary}

Create a comprehensive progress report including:

1. Overall completion percentage
2. Critical path status
3. Blockers and issues
4. Time estimates (remaining vs original)
5. Quality metrics
6. Recommendations for next steps

Format as JSON:
{{
    "overall_progress": {{
        "completion_percentage": 65,
        "tasks_total": 10,
        "tasks_completed": 6,
        "tasks_in_progress": 3,
        "tasks_failed": 1
    }},
    "critical_path": {{
        "status": "on_track|delayed|blocked",
        "current_task": "task_name",
        "blockers": ["blocker1"],
        "estimated_delay_minutes": 0
    }},
    "time_analysis": {{
        "elapsed_minutes": 45,
        "estimated_remaining_minutes": 30,
        "original_estimate_minutes": 60,
        "efficiency_ratio": 0.8
    }},
    "quality_metrics": {{
        "success_rate": 0.86,
        "retry_count": 2,
        "error_rate": 0.14
    }},
    "issues": [
        {{
            "severity": "high|medium|low",
            "task": "task_name",
            "description": "Issue description",
            "impact": "Impact on project"
        }}
    ],
    "recommendations": [
        {{
            "action": "Recommended action",
            "reason": "Why this is recommended",
            "priority": "high|medium|low"
        }}
    ]
}}""",
    variables=["active_tasks_json", "completed_tasks_json", "failed_tasks_json", 
               "project_summary"],
)


# Prompt selection functions
def get_decomposition_prompt(prompt_type: str) -> PromptTemplate:
    """Get a specific decomposition prompt template.
    
    Args:
        prompt_type: Type of prompt needed
        
    Returns:
        Corresponding prompt template
    """
    prompts = {
        "task_analysis": TASK_ANALYSIS_PROMPT,
        "dependency_analysis": DEPENDENCY_ANALYSIS_PROMPT,
        "task_specification": TASK_SPECIFICATION_PROMPT,
        "complexity_estimation": COMPLEXITY_ESTIMATION_PROMPT,
        "progress_aggregation": PROGRESS_AGGREGATION_PROMPT,
    }
    
    if prompt_type not in prompts:
        raise ValueError(f"Unknown prompt type: {prompt_type}")
    
    return prompts[prompt_type]


def create_custom_decomposition_prompt(
    objective: str,
    context: Dict[str, Any]
) -> PromptTemplate:
    """Create a custom decomposition prompt for specific scenarios.
    
    Args:
        objective: What the prompt should achieve
        context: Additional context for the prompt
        
    Returns:
        Customized prompt template
    """
    template = f"""You are an expert software architect with a specific objective.

OBJECTIVE: {objective}

CONTEXT:
{dict_to_formatted_string(context)}

{{user_input}}

Provide your analysis in structured JSON format appropriate for the objective.
Consider all context provided and ensure your response is actionable and specific."""
    
    return PromptTemplate(
        id=uuid4(),
        name=f"custom_{objective.lower().replace(' ', '_')}",
        template=template,
        variables=["user_input"],
    )


def dict_to_formatted_string(d: Dict[str, Any], indent: int = 0) -> str:
    """Convert dictionary to formatted string for prompts.
    
    Args:
        d: Dictionary to format
        indent: Indentation level
        
    Returns:
        Formatted string representation
    """
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