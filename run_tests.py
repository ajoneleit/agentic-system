#!/usr/bin/env python3
"""Test runner that sets up the Python path correctly."""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Now run the tests
if __name__ == "__main__":
    import pytest
    
    # Run the verification tests
    test_file = "tests/test_verification_system.py"
    
    print(f"Running tests from {test_file}")
    print(f"Python path includes: {project_root}")
    
    # Run pytest on the test file
    exit_code = pytest.main([test_file, "-v"])
    sys.exit(exit_code)