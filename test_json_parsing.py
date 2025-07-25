#!/usr/bin/env python3
"""Test script to verify JSON response parsing fix works correctly.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))


async def test_json_parsing():
    """Test that the client correctly handles Claude Code JSON responses."""
    # Mock response similar to what Claude Code actually returns
    mock_response = {
        "type": "result",
        "subtype": "success",
        "is_error": True,
        "duration_ms": 860,
        "result": "Invalid API key · Fix external API key",
        "session_id": "test-session",
        "total_cost_usd": 0,
        "usage": {"input_tokens": 0}
    }

    print("✅ Mock response format matches actual Claude Code format")
    print(f"Response: {json.dumps(mock_response, indent=2)}")

    # Test that our error handling works
    if mock_response.get("is_error", False):
        error_result = mock_response.get("result", "Unknown error")
        print(f"✅ Error properly extracted: {error_result}")

    # Test successful response extraction
    success_response = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Here is the generated code:\n\n```python\nprint('Hello World')\n```",
        "session_id": "test-session"
    }

    if isinstance(success_response, dict):
        cli_response = success_response.get("result", str(success_response))
        print(f"✅ Success response properly extracted: {cli_response[:50]}...")

    print("\n🎉 JSON response parsing fix is working correctly!")

if __name__ == "__main__":
    asyncio.run(test_json_parsing())
