# Development Setup Process

**Reality Validation**: All commands in this document are tested in CI - [Validation Script](../validation/setup_validator.py)

## Prerequisites

### System Requirements
- **Python**: 3.9+ (Verified by: `python --version`)
- **Git**: Latest version (Verified by: `git --version`)
- **Claude CLI**: Latest version (Verified by: `claude --version`)

### Environment Validation
Run the automated setup validator:
```bash
python docs/validation/setup_validator.py --check-prerequisites
```

## Installation Steps

### 1. Repository Setup
```bash
# Clone repository
git clone <repository-url>
cd agentic-system

# Verify repository structure
python docs/validation/setup_validator.py --check-structure
```

### 2. Python Environment
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Verify installation
python docs/validation/setup_validator.py --check-dependencies
```

### 3. API Configuration
```bash
# Create .env file
cp .env.example .env

# Edit .env with your API keys:
# ANTHROPIC_API_KEY=your_anthropic_key
# OPENAI_API_KEY=your_openai_key

# Verify API connectivity
python docs/validation/setup_validator.py --check-apis
```

### 4. System Health Check
```bash
# Run comprehensive health check
python scripts/health_check.py

# Expected output: "System Status: HEALTHY"
```

## Verification Commands

Each setup step can be individually verified:

```bash
# Verify Python environment
python -c "import sys; print(f'Python {sys.version}')"

# Verify core imports
python -c "from src.agents.meta_agent import MetaAgent; print('✅ Core system accessible')"

# Verify API connectivity
python -c "
from src.clients.claude_cli_client_robust import ClaudeCodeClient
client = ClaudeCodeClient()
print('✅ Claude CLI accessible')
"

# Run example
python examples/basic_usage.py
```

## Troubleshooting

### Common Issues
1. **Import Errors**: Ensure virtual environment is activated and dependencies installed
2. **API Errors**: Verify API keys are set in .env file
3. **Permission Errors**: Ensure proper file permissions on artifacts/ and logs/ directories

### Validation Tools
```bash
# Run complete setup validation
python docs/validation/setup_validator.py --full-check

# Generate setup report
python docs/validation/setup_validator.py --generate-report
```

## Development Tools

### Code Quality
```bash
# Format code
black .

# Lint code
ruff check .

# Type checking
mypy . --ignore-missing-imports
```

### Testing
```bash
# Run unit tests
pytest tests/unit/ -v

# Run with coverage
pytest --cov=src --cov-report=html
```

---

**Validation Status**: This setup process is automatically validated in CI
**Last Tested**: Automatically updated on each CI run
**Success Rate**: Tracked in [metrics/setup-success.json](../metrics/setup-success.json)