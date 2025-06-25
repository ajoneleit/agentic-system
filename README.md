# Agentic Coding System

An advanced autonomous coding system that uses multiple Claude instances to generate, verify, and improve code through intelligent agents. The system employs a hierarchical agent structure with parallel processing capabilities and comprehensive verification loops to achieve 100% code quality.

## Features

- **Hierarchical Agent Architecture**: Meta agent orchestrates specialized sub-agents for different tasks
- **Parallel Task Execution**: Multiple agents work simultaneously on independent tasks
- **Comprehensive Verification**: Dual verification system with compilation and test checks
- **Continuous Learning**: Learns from execution patterns to improve future performance
- **Prompt Evolution**: Dynamic prompt refinement based on task outcomes
- **Robust Error Handling**: Automatic repair loops for failed tasks
- **Production-Ready**: Async support, rate limiting, retry logic, and extensive logging

## Architecture Overview

```
┌─────────────────┐
│   Meta Agent    │ ← Orchestrates entire system
└────────┬────────┘
         │
    ┌────┴────────────────────────────┐
    │                                  │
┌───▼─────┐ ┌───────────┐ ┌──────────▼─┐ ┌──────────────┐
│  Core   │ │  Testing  │ │    Doc     │ │ Optimization │
│  Logic  │ │   Agent   │ │   Agent    │ │    Agent     │
│  Agent  │ │           │ │            │ │              │
└─────────┘ └───────────┘ └────────────┘ └──────────────┘
    │            │              │               │
    └────────────┴──────┬───────┴───────────────┘
                        │
                ┌───────▼────────┐
                │   Artifacts    │
                │   Management   │
                └───────┬────────┘
                        │
              ┌─────────┴──────────┐
              │                    │
        ┌─────▼──────┐      ┌─────▼──────┐
        │ Compiler   │      │    Test    │
        │ Verifier   │      │  Verifier  │
        └────────────┘      └────────────┘
```

## Quick Start

### Prerequisites

- Python 3.9 or higher
- Anthropic API key

### Installation

1. Clone the repository:
```bash
git clone https://github.com/agentic-system/agentic-coding-system.git
cd agentic-coding-system
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your Anthropic API key
```

### Basic Usage

```python
import asyncio
from src.clients.claude_client import ClaudeClient
from config import get_settings, ClaudeModel

async def main():
    settings = get_settings()
    
    # Initialize Claude client
    async with ClaudeClient() as client:
        # Create a message
        response = await client.create_message(
            model=ClaudeModel.SONNET,
            messages=[
                {"role": "user", "content": "Write a Python function to calculate fibonacci numbers"}
            ],
            max_tokens=1000,
        )
        
        print(response.content[0].text)

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

The system uses a hierarchical configuration approach:

1. **Environment Variables**: Highest priority, prefixed with `ACS_`
2. **Configuration Files**: YAML files in the `config/` directory
3. **Default Values**: Built-in defaults in the code

### Key Configuration Options

```yaml
# config/settings.yaml
api:
  timeout: 300
  max_retries: 3
  rate_limit_per_minute: 50

agent:
  max_parallel_agents: 10
  default_model: claude-3-sonnet-20240229
  meta_agent_model: claude-3-opus-20240229
  verification_timeout: 600
  max_repair_attempts: 5

verification:
  enable_compilation_check: true
  enable_test_verification: true
  minimum_coverage: 90.0
  strict_mode: true

learning:
  enable_learning: true
  pattern_threshold: 3
  memory_retention_days: 30
```

## Development

### Project Structure

```
agentic-coding-system/
├── src/
│   ├── core/           # Core interfaces and abstractions
│   ├── agents/         # Agent implementations
│   ├── clients/        # API clients (Claude)
│   ├── verification/   # Verification system
│   ├── learning/       # Learning engine
│   ├── artifacts/      # Artifact management
│   └── utils/          # Utilities and helpers
├── tests/              # Test suite
├── config/             # Configuration files
├── docs/               # Documentation
└── scripts/            # Utility scripts
```

### Running Tests

```bash
# Quick test run
./run_tests.sh

# Run tests with coverage report
./run_tests_with_coverage.sh

# Run tests manually
source agentic-env/bin/activate
python -m pytest tests/ -v

# Run with coverage manually
python -m pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Format code
black src tests

# Lint code
ruff check src tests

# Type checking
mypy src
```

## Advanced Features

### Artifact Management System

The system includes a comprehensive artifact management system with versioning, caching, and dependency tracking:

```python
from src.core.artifact_manager import ArtifactManager
from src.core.interfaces import Artifact, ArtifactType

# Initialize artifact manager
manager = ArtifactManager(
    storage_path=Path("./artifacts"),
    max_memory_cache_size=100,
    enable_compression=True
)
await manager.initialize()

# Store an artifact
artifact = Artifact(
    name="calculator.py",
    type=ArtifactType.SOURCE_CODE,
    content="def add(a, b): return a + b",
    language="python"
)
stored = await manager.store_artifact(artifact)

# Update creates a new version
updated = await manager.update_artifact(
    artifact.id,
    new_content="def add(a, b): return a + b\ndef subtract(a, b): return a - b",
    reason="Added subtract function"
)

# Retrieve specific version
v1 = await manager.get_artifact(artifact.id, version=1)

# Search artifacts
results = await manager.search_artifacts(
    language="python",
    tags={"calculator"}
)
```

Key features:
- **Centralized Storage**: All artifacts in one managed location
- **Version Control**: Git-like versioning with branches and merges
- **Memory Caching**: LRU cache for frequently accessed artifacts
- **Compression**: Optional gzip compression for storage efficiency
- **Atomic Operations**: Thread-safe file operations
- **Dependency Tracking**: Automatic dependency detection and impact analysis

### Parallel Task Execution

The system can execute multiple independent tasks simultaneously:

```python
from src.core.interfaces import Task, TaskPriority

# Tasks are automatically parallelized when possible
tasks = [
    Task(name="Implement API endpoint", priority=TaskPriority.HIGH),
    Task(name="Write unit tests", priority=TaskPriority.HIGH),
    Task(name="Generate documentation", priority=TaskPriority.MEDIUM),
]

# Meta agent will assign these to different sub-agents for parallel execution
```

### Custom Verification Strategies

Implement custom verifiers for specific requirements:

```python
from src.core.interfaces import Verifier, Artifact

class SecurityVerifier(Verifier):
    async def verify(self, artifact: Artifact) -> Dict[str, Any]:
        # Custom security checks
        vulnerabilities = await self.scan_for_vulnerabilities(artifact)
        return {
            "success": len(vulnerabilities) == 0,
            "errors": vulnerabilities,
            "metrics": {"security_score": self.calculate_score(artifact)}
        }
```

### Learning System Integration

The system learns from each execution to improve future performance:

```python
from src.learning.engine import LearningEngine

engine = LearningEngine()

# Record execution patterns
await engine.record_execution(
    task=completed_task,
    prompt_used=prompt_template,
    execution_time=duration,
    success=True,
    artifacts=produced_artifacts
)

# Get recommendations for similar tasks
recommendations = await engine.get_recommendations(new_task)
```

## API Reference

### Core Classes

- `Agent`: Base class for all agents
- `Task`: Represents a unit of work
- `Artifact`: Code artifacts produced by agents
- `Verifier`: Base class for verification components
- `PromptTemplate`: Templates for agent prompts

### Key Methods

#### ClaudeClient

- `create_message()`: Send a message to Claude
- `stream_message()`: Stream responses from Claude
- `create_message_with_retry()`: Message with automatic retry

#### MetaAgent

- `decompose_task()`: Break down user requests into tasks
- `spawn_agent()`: Create specialized sub-agents
- `monitor_progress()`: Track system progress

## Monitoring and Observability

The system provides comprehensive logging and metrics:

```python
from src.utils.app_logging import get_logger, LogContext

logger = get_logger(__name__)

# Structured logging with context
with LogContext(task_id=task.id, agent_role=agent.role):
    logger.info("Starting task execution")
```