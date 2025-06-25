#!/bin/bash
# Quick test runner without coverage

echo "Running tests..."

# Activate virtual environment
source agentic-env/bin/activate

# Run tests
python -m pytest tests/ -v -q

echo "Done."