# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an architectural planning project for an autonomous agentic coding system. The repository is currently in the design phase with only the system architecture documented in `system_plan.md`.

## Project Status

**Current Phase**: Planning/Design
- No implementation code exists yet
- No build/test infrastructure established
- Repository contains only architectural documentation

## System Architecture

The planned system implements a hierarchical agent structure for autonomous code generation and verification:

### Core Components
1. **Meta Agent (Task Manager)**: Orchestrates sub-agents, manages task decomposition, and maintains global context
2. **Sub-Agents**: Execute specific coding tasks (Core Logic, Testing, Documentation, Optimization)
3. **Artifact Management System**: Centralized storage with version control and dependency tracking
4. **Dual Verification System**: 
   - Compiler Verification (syntax/compilation)
   - Test Verification (functional/integration testing)
5. **Meta Repair Loop**: Analyzes failures and generates targeted repair tasks

### Key Architectural Principles
- Parallel task execution with multiple sub-agents
- Continuous verification loops until 100% success
- Dynamic prompt refinement based on progress and failures
- Atomic artifact updates to prevent inconsistent states

## Development Guidelines

Since this is a greenfield project, when implementing:

1. **Start with Core Infrastructure**:
   - Choose appropriate programming language(s) based on system requirements
   - Set up project structure following the hierarchical agent architecture
   - Implement the Artifact Management System first as it's foundational

2. **Verification System Priority**:
   - Both compiler and test verification are critical for the 100% success requirement
   - Build these systems early to enable the verification-repair loop

3. **Agent Communication**:
   - Design clear interfaces between Meta Agent and Sub-Agents
   - Implement robust error handling and feedback mechanisms
   - Ensure parallel execution doesn't create race conditions

4. **Success Metrics**:
   - All code must achieve 100% compilation success
   - All tests must pass (100% pass rate)
   - Minimum 90% code coverage (configurable)
   - Human approval required for final validation

## Development Commands

### Health Check
Run the system health check to ensure everything is configured correctly:
```bash
python scripts/health_check.py
```

This validates:
- Python version compatibility (3.9+)
- Required directories exist
- Configuration is valid
- API keys are configured
- Claude API connectivity
- All dependencies are installed

### Running Examples
```bash
python examples/basic_usage.py
```

### Running Tests
```bash
pytest                          # Run all tests
pytest tests/unit/             # Run unit tests only
pytest -v                      # Verbose output
```

## Next Steps

When beginning implementation:
1. Run health check to ensure setup is correct: `python scripts/health_check.py`
2. Copy `.env.example` to `.env` and add your Anthropic API key
3. Implement basic Meta Agent orchestration logic
4. Build simple Sub-Agent framework
5. Establish testing and verification infrastructure