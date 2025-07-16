# Claude CLI Integration with MCP

This document describes the seamless integration of Claude CLI with MCP (Model Context Protocol) into the existing agentic coding system.

## Overview

The integration enhances the agentic system by:
- **Meta Agent**: Always uses Claude API with Opus 3 model for orchestration
- **Sub-agents**: Can use Claude CLI with MCP tools for enhanced file operations
- **Quality Gates**: Validates all CLI outputs before acceptance
- **Feedback Loops**: Iteratively improves outputs that don't meet quality standards

## Architecture

```
┌─────────────────┐
│   Meta Agent    │ ← Always uses Claude API (Opus 3)
│  (Orchestrator) │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Task    │
    │ Manager │
    └────┬────┘
         │
    ┌────┴─────────────┬─────────────┬──────────────┐
    ▼                  ▼             ▼              ▼
┌─────────┐      ┌──────────┐  ┌──────────┐  ┌────────────┐
│Core Logic│      │Testing   │  │Document  │  │Optimization│
│ Agent    │      │Agent     │  │Agent     │  │Agent       │
└─────────┘      └──────────┘  └──────────┘  └────────────┘
     ↓                ↓              ↓              ↓
  Claude CLI       Claude CLI    Claude CLI    Claude CLI
  with MCP         with MCP      with MCP      with MCP
```

## Key Components

### 1. Enhanced Claude Client (`src/clients/claude_client.py`)

The unified client automatically selects between API and CLI:

```python
claude_client = ClaudeClient(use_cli_for_subagents=True)

# Meta Agent request - uses API
response = await claude_client.create_message(
    model=ClaudeModel.OPUS,
    messages=[{"role": "user", "content": "Decompose this task"}],
    agent_role="meta_agent"  # Forces API usage
)

# Sub-agent request - uses CLI
response = await claude_client.create_message(
    model=ClaudeModel.SONNET,
    messages=[{"role": "user", "content": "Generate code"}],
    agent_role="core_logic",  # Uses CLI with MCP tools
    agent_name="code_generator_001"
)
```

### 2. MCP Tool Permissions

Each agent role has specific MCP tool permissions:

- **Core Logic**: Read, Write, Edit, Grep
- **Testing**: Read, Write, Bash (for test execution), Grep
- **Documentation**: Read, Write, Edit
- **Optimization**: Read, Edit, Bash, Grep
- **Security**: Read, Grep, Bash

### 3. Quality Gates System

All CLI outputs pass through quality validation:

```python
quality_result = await quality_gates.validate_cli_output(
    output=cli_response,
    task=task_info,
    requirements={
        "min_code_quality": 0.8,
        "min_security_score": 0.9,
        "min_test_coverage": 0.7
    }
)
```

Quality metrics include:
- Code quality (syntax, style, error handling)
- Security scanning (dangerous patterns)
- Test coverage estimation
- Documentation completeness
- Complexity analysis

### 4. Feedback Loop System

When outputs don't meet quality standards:

```python
decision = await feedback_loop.evaluate_output(
    output=cli_output,
    task=task,
    quality_result=quality_result
)

if decision.action == FeedbackAction.RETRY:
    # Retry with improvement prompt
    improved_output = await retry_with_feedback(decision.improvement_prompt)
elif decision.action == FeedbackAction.ESCALATE:
    # Escalate to specialist agent
    specialist_output = await escalate_to_specialist(decision.target_agent)
```

## Configuration

### Environment Variables (.env)

```bash
# Enable CLI for sub-agents
ACS_CLI__USE_CLI_FOR_SUBAGENTS=true

# CLI settings
ACS_CLI__CLI_PATH=claude
ACS_CLI__MCP_CONFIG_PATH=mcp-config.json
ACS_CLI__CLI_TIMEOUT_SECONDS=600
ACS_CLI__CLI_MAX_MEMORY_MB=2048

# Quality gates
ACS_CLI__ENABLE_QUALITY_GATES=true
ACS_CLI__MIN_CODE_QUALITY_SCORE=0.8
ACS_CLI__MIN_TEST_COVERAGE=0.7
ACS_CLI__MAX_SECURITY_ISSUES=0

# Feedback loop
ACS_CLI__ENABLE_FEEDBACK_LOOP=true
ACS_CLI__MAX_IMPROVEMENT_ITERATIONS=3
ACS_CLI__FEEDBACK_SCORE_THRESHOLD=0.95
```

### MCP Configuration (mcp-config.json)

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "mcp-server-filesystem",
      "args": ["--workspace", "./workspace"],
      "capabilities": ["read", "write", "edit", "list"]
    },
    "bash": {
      "command": "mcp-server-bash",
      "args": ["--safe-mode"],
      "capabilities": ["execute"]
    },
    "git": {
      "command": "mcp-server-git",
      "args": ["--repo", "./"],
      "capabilities": ["status", "diff", "commit"]
    }
  },
  "security": {
    "maxMemoryMB": 2048,
    "timeout": 600,
    "allowedPaths": ["./workspace", "./artifacts", "./tests"]
  }
}
```

## Usage Example

```python
# Initialize with CLI support
settings = get_settings()
settings.cli.use_cli_for_subagents = True

# Create enhanced client
claude_client = ClaudeClient()

# Meta Agent processes request (uses API)
meta_agent = MetaAgent(claude_client=claude_client)
result = await meta_agent.process_request(
    "Create a REST API with authentication"
)

# Behind the scenes:
# 1. Meta Agent (API/Opus 3) decomposes task
# 2. Sub-agents (CLI/MCP) execute with file operations
# 3. Quality gates validate outputs
# 4. Feedback loop improves if needed
# 5. Results aggregated and returned
```

## Benefits

1. **Enhanced Capabilities**: Sub-agents can directly manipulate files and execute commands
2. **Quality Assurance**: All outputs validated before acceptance
3. **Iterative Improvement**: Automatic retry with feedback for better results
4. **Security**: Sandboxed execution with permission controls
5. **Flexibility**: Seamless fallback to API if CLI unavailable
6. **Performance**: Memory-safe streaming prevents resource exhaustion

## Monitoring

The system provides detailed metrics:

```python
metrics = claude_client.get_metrics()
# {
#     "total_requests": 42,
#     "cli_enabled": true,
#     "cli_available": true,
#     "average_quality_score": 0.92,
#     "retry_rate": 0.15
# }
```

## Error Handling

The system gracefully handles various failure modes:

1. **CLI Unavailable**: Falls back to API
2. **Quality Failures**: Triggers feedback loop
3. **Security Issues**: Escalates to security specialist
4. **Resource Limits**: Enforces memory and timeout constraints
5. **API Limits**: Retries with exponential backoff

## Best Practices

1. **Always use API for Meta Agent**: Ensures reliable orchestration
2. **Enable quality gates**: Maintains code standards
3. **Configure appropriate timeouts**: Prevents hanging processes
4. **Monitor resource usage**: Adjust memory limits as needed
5. **Review security permissions**: Limit MCP tools per agent role

## Testing

Run the demonstration:

```bash
python demo_claude_cli_integration.py
```

This shows:
- Automatic API/CLI selection
- Quality validation in action
- Feedback loop improvements
- Resource monitoring

## Conclusion

The Claude CLI integration provides powerful new capabilities while maintaining the robustness and reliability of the original system. Meta Agent continues using the API for orchestration, while sub-agents gain direct file manipulation abilities through MCP tools, all with comprehensive quality and security controls.