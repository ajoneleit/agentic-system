# Autonomous AI Coding System

A sophisticated multi-agent system that uses Claude AI to autonomously generate, verify, and improve code through intelligent orchestration and continuous verification loops.

## Project Overview

The **Autonomous AI Coding System** is a production-ready platform that coordinates multiple AI agents to create complete software projects. The system employs a hierarchical architecture with specialized agents that work together to achieve 100% code quality through continuous verification and automated repair loops.

### Key Features

- **Multi-Agent Architecture**: Hierarchical system with Meta Agent orchestration and specialized Sub-Agents
- **Continuous Verification**: Dual verification system (compilation + testing) ensures code quality
- **Intelligent Repair**: Automated failure analysis and repair loops
- **Parallel Processing**: Multiple agents work simultaneously for efficiency
- **Comprehensive Artifacts**: Version-controlled storage of all generated code
- **Production Ready**: Async processing, error handling, monitoring, and observability

## Architecture Overview

### Core Components

1. **Meta Agent (Task Manager)**
   - Orchestrates the entire system using OpenAI O3 for task decomposition
   - Coordinates multiple sub-agents and manages global context
   - Implements intelligent retry and repair mechanisms

2. **Sub-Agents** (Always use Claude Code)
   - **Core Logic Agent**: Generates main application code
   - **Testing Agent**: Creates comprehensive test suites
   - **Documentation Agent**: Writes documentation and README files
   - **Optimization Agent**: Improves code performance and quality
   - **Verification Agent**: Validates code and runs quality checks

3. **Verification System**
   - **Compiler Verification**: Syntax checking and compilation validation
   - **Test Verification**: Automated test execution and coverage analysis
   - **Quality Gates**: Configurable quality thresholds

4. **Artifact Management**
   - Version-controlled storage with compression
   - Dependency tracking and metadata management
   - Hierarchical organization with UUID-based indexing

5. **Communication Hub**
   - Inter-agent messaging and coordination
   - Shared context management
   - Event-driven architecture

## Installation & Setup

### Prerequisites

- Python 3.9 or higher
- Anthropic API key (for Claude)
- OpenAI API key (for Meta Agent)
- Claude Code CLI tool installed

### Installation Steps

1. **Clone the repository**
   ```bash
   git clone https://github.com/agentic-system/agentic-coding-system.git
   cd agentic-coding-system
   ```

2. **Set up virtual environment**
   ```bash
   python -m venv agentic-env
   source agentic-env/bin/activate  # On Windows: agentic-env\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   # Or using pyproject.toml
   pip install -e .
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys:
   # ANTHROPIC_API_KEY=your_claude_api_key
   # OPENAI_API_KEY=your_openai_api_key
   ```

5. **Run health check**
   ```bash
   python scripts/health_check.py
   ```

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run code formatting
black src/ tests/
ruff check src/ tests/

# Run type checking
mypy src/
```

## Usage Guide

### Basic Usage

```python
from src.agents.meta_agent import MetaAgent
import asyncio

async def main():
    meta_agent = MetaAgent()
    
    # Simple code generation
    result = await meta_agent.process_request(
        "Create a Python calculator with tests"
    )
    
    print(f"Project created: {result.project_id}")
    print(f"Files generated: {len(result.artifacts)}")

asyncio.run(main())
```

### Command Line Interface

```bash
# Run a simple example
python examples/basic_usage.py

# Run the main demo
python demo_agentic_system.py

# Health check
python scripts/health_check.py
```

### Advanced Usage

```python
from src.agents.meta_agent import MetaAgent
from src.core.interfaces import TaskContext
import asyncio

async def advanced_example():
    meta_agent = MetaAgent()
    
    # Create custom task context
    context = TaskContext(
        project_id="my-custom-project",
        base_path="/path/to/workspace",
        settings={
            "max_parallel_tasks": 4,
            "verification_enabled": True,
            "test_coverage_threshold": 90
        }
    )
    
    # Process complex request
    result = await meta_agent.process_request(
        request="Create a REST API with PostgreSQL backend, include authentication, CRUD operations, and comprehensive tests",
        context=context
    )
    
    # Access results
    for artifact in result.artifacts:
        print(f"Generated: {artifact.file_path} ({artifact.type})")

asyncio.run(advanced_example())
```

## Components Documentation

### Meta Agent

The Meta Agent serves as the central orchestrator:

- **Task Decomposition**: Uses OpenAI O3 to break complex requests into manageable tasks
- **Agent Coordination**: Manages sub-agent lifecycle and task assignment
- **Quality Assurance**: Ensures 100% compilation and test success
- **Failure Recovery**: Implements intelligent retry and repair mechanisms

**Configuration Options**:
- `max_parallel_tasks`: Maximum concurrent sub-agents (default: 3)
- `retry_attempts`: Number of retry attempts for failed tasks (default: 3)
- `verification_required`: Enable/disable verification loops (default: True)

### Sub-Agents

All sub-agents use Claude Code for enhanced capabilities:

#### Core Logic Agent
- Generates main application code
- Implements business logic and data structures
- Follows coding best practices and patterns

#### Testing Agent
- Creates comprehensive test suites
- Generates unit, integration, and end-to-end tests
- Ensures high code coverage

#### Documentation Agent
- Writes technical documentation
- Creates README files and code comments
- Generates API documentation

### Verification System

The verification system ensures code quality through multiple stages:

1. **Syntax Verification**: AST parsing and syntax checking
2. **Compilation Verification**: Full compilation testing
3. **Test Execution**: Automated test running with coverage analysis
4. **Quality Gates**: Configurable quality thresholds

**Supported Languages**:
- Python (pytest, coverage)
- JavaScript (Jest, Mocha)
- TypeScript (tsc, Jest)

### Artifact Management

All generated code is stored as versioned artifacts:

- **Compression**: Gzip compression for efficient storage
- **Metadata**: Full tracking of creation, modification, and dependencies
- **Versioning**: Complete version history with rollback capabilities
- **Integrity**: SHA256 checksums for corruption detection

## Configuration

### Environment Variables

```bash
# API Configuration
ANTHROPIC_API_KEY=your_claude_api_key
OPENAI_API_KEY=your_openai_api_key

# System Configuration
MAX_PARALLEL_TASKS=3
VERIFICATION_ENABLED=true
TEST_COVERAGE_THRESHOLD=90

# Storage Configuration
ARTIFACTS_BASE_PATH=./artifacts
PROJECTS_BASE_PATH=./projects

# Logging Configuration
LOG_LEVEL=INFO
LOG_FORMAT=json
```

### Settings Files

Configuration is managed through Pydantic settings:

```python
# config/settings.py
class Settings(BaseSettings):
    # API Settings
    anthropic_api_key: str
    openai_api_key: str
    
    # Agent Settings
    max_parallel_tasks: int = 3
    retry_attempts: int = 3
    
    # Verification Settings
    verification_enabled: bool = True
    test_coverage_threshold: int = 90
    
    class Config:
        env_file = ".env"
```

## Testing

### Test Structure

```
tests/
├── unit/                   # Unit tests for individual components
├── integration/           # Integration tests
├── test_agents.py        # Agent system tests
├── test_verification.py  # Verification system tests
└── test_artifacts.py     # Artifact management tests
```

### Running Tests

```bash
# Run all tests
pytest

# Run specific test categories
pytest tests/unit/              # Unit tests only
pytest tests/integration/       # Integration tests only

# Run with coverage
pytest --cov=src --cov-report=html

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_agents.py -v
```

### Test Configuration

```bash
# pytest.ini
[tool:pytest]
testpaths = tests
asyncio_mode = auto
filterwarnings = 
    error
    ignore::UserWarning
    ignore::DeprecationWarning
addopts = 
    --strict-markers
    --tb=short
```

## API Reference

### MetaAgent API

```python
class MetaAgent:
    async def process_request(
        self,
        request: str,
        context: Optional[TaskContext] = None
    ) -> TaskResult:
        """Process a complete user request."""
        
    async def decompose_task(
        self,
        request: str
    ) -> List[Task]:
        """Break down request into executable tasks."""
        
    async def coordinate_execution(
        self,
        tasks: List[Task]
    ) -> List[TaskResult]:
        """Coordinate task execution across agents."""
```

### Sub-Agent API

```python
class SubAgent(Agent):
    async def execute_task(
        self,
        task: Task,
        context: TaskContext
    ) -> TaskResult:
        """Execute a specific task."""
        
    async def verify_result(
        self,
        result: TaskResult
    ) -> VerificationResult:
        """Verify task execution result."""
```

### Artifact Manager API

```python
class ArtifactManager:
    async def store_artifact(
        self,
        artifact: Artifact
    ) -> str:
        """Store an artifact and return its ID."""
        
    async def retrieve_artifact(
        self,
        artifact_id: str
    ) -> Artifact:
        """Retrieve an artifact by ID."""
        
    async def list_artifacts(
        self,
        project_id: Optional[str] = None
    ) -> List[Artifact]:
        """List artifacts, optionally filtered by project."""
```

## Development

### Code Organization

```
src/
├── agents/          # Agent implementations
├── core/           # Core system components
├── clients/        # API clients (Claude, OpenAI)
├── verification/   # Verification system
├── utils/          # Utility functions
└── prompts/        # AI prompts and templates
```

### Development Workflow

1. **Code Style**: Uses Black for formatting, Ruff for linting
2. **Type Checking**: MyPy for static type analysis
3. **Testing**: Pytest with async support and coverage
4. **Documentation**: Docstrings and type hints throughout
5. **Version Control**: Git with conventional commits

### Contributing Guidelines

1. **Fork the repository**
2. **Create feature branch**: `git checkout -b feature/new-feature`
3. **Follow code style**: Run `black` and `ruff` before committing
4. **Add tests**: Ensure new code has test coverage
5. **Update documentation**: Update README and docstrings
6. **Submit pull request**: Include description of changes

## Monitoring & Observability

### Logging

The system uses structured logging with multiple output formats:

```python
import structlog

logger = structlog.get_logger(__name__)

# Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
logger.info("Task completed", task_id=task_id, duration=duration)
```

### Metrics

Key metrics tracked:
- Task completion rates
- Agent performance
- Verification success rates
- API usage and costs
- System health indicators

### Health Checks

```bash
# Run comprehensive health check
python scripts/health_check.py

# Check specific components
python scripts/health_check.py --component agents
python scripts/health_check.py --component verification
```

## Troubleshooting

### Common Issues

#### 1. API Key Issues
```bash
# Check API key configuration
python -c "from config import get_settings; print(get_settings().anthropic_api_key[:10])"

# Test API connectivity
python scripts/health_check.py
```

#### 2. Claude Code CLI Not Found
```bash
# Install Claude Code CLI
# Follow instructions at https://docs.anthropic.com/claude/docs/claude-code

# Verify installation
claude --version
```

#### 3. Verification Failures
```bash
# Check verification configuration
python -c "from config import get_settings; print(get_settings().verification_enabled)"

# Run verification tests
pytest tests/test_verification.py -v
```

#### 4. Memory Issues
```bash
# Check system resources
python scripts/health_check.py --resource-check

# Reduce parallel tasks
export MAX_PARALLEL_TASKS=1
```

### Error Messages

- **`CLINotAvailableError`**: Claude Code CLI not installed or not in PATH
- **`APIKeyError`**: Invalid or missing API keys
- **`VerificationError`**: Code failed verification checks
- **`TaskTimeoutError`**: Task execution exceeded timeout
- **`ArtifactCorruptionError`**: Artifact integrity check failed

### Debug Mode

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
python your_script.py
```

## Performance Considerations

### Optimization Settings

```python
# Recommended production settings
MAX_PARALLEL_TASKS=3          # Balance between speed and resource usage
VERIFICATION_ENABLED=true     # Always verify in production
TEST_COVERAGE_THRESHOLD=90    # High quality threshold
```

### Resource Requirements

- **Memory**: 4GB+ recommended for concurrent operations
- **CPU**: 2+ cores for parallel processing
- **Disk**: 1GB+ for artifact storage
- **Network**: Stable connection for API calls

## System Status

### Current Implementation Status

- ✅ **Core Architecture**: Fully implemented
- ✅ **Agent System**: Complete with Meta Agent and Sub-Agents
- ✅ **Verification System**: Comprehensive verification pipeline
- ✅ **Artifact Management**: Full versioning and storage
- ✅ **API Integration**: Claude and OpenAI client support
- ✅ **Testing Infrastructure**: Extensive test coverage
- ✅ **Documentation**: Complete API and usage documentation

### Generated Projects

The system has successfully generated 200+ projects including:
- Hello World applications
- Calculators and mathematical tools
- Weather applications (CLI and desktop)
- REST APIs with PostgreSQL backends
- Todo list applications
- Complex multi-component systems

### Version Information

- **Version**: 0.1.0
- **Python**: 3.9+
- **License**: MIT
- **Status**: Alpha (Production Ready)

## Acknowledgments

Built with:
- **Claude AI** by Anthropic for code generation
- **OpenAI GPT** for task decomposition
- **Python** ecosystem for implementation
- **pytest** for testing framework
- **Pydantic** for configuration management
- **NetworkX** for dependency management
