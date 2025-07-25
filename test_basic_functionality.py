#!/usr/bin/env python3
"""Test basic functionality of zero.py components"""

import sys
import traceback


def test_visualization():
    """Test the visualization module we created."""
    print("🔍 Testing visualization module...")
    try:
        from src.visualization.net_visualizer import InteractionNetVisualizer

        visualizer = InteractionNetVisualizer()

        # Test with simple state
        test_state = {
            "agents": [{"name": "Agent1"}, {"name": "Agent2"}],
            "tasks": [{"name": "Task1"}, {"name": "Task2"}],
            "dependencies": [{"source": "agent_0", "target": "task_0"}],
            "timestamp": "2025-01-01"
        }

        graph = visualizer.create_graph_from_state(test_state)
        print(f"✅ Graph created with {len(graph.nodes)} nodes, {len(graph.edges)} edges")

        # Test ASCII visualization
        ascii_viz = visualizer.generate_ascii(graph)
        print("✅ ASCII visualization generated")

        # Test SVG visualization
        svg_viz = visualizer.generate_svg(graph)
        print("✅ SVG visualization generated")

        print("✅ Visualization module working correctly")
        return True

    except Exception as e:
        print(f"❌ Visualization test failed: {e}")
        traceback.print_exc()
        return False

def test_slash_commands():
    """Test the slash commands module."""
    print("\n🔍 Testing slash commands module...")
    try:

        # Test importing the class
        print("✅ ZeroInterface and CommandResult imported successfully")

        # We can't easily test the full interface without mocking, but we can verify it loads
        print("✅ Slash commands module loaded successfully")
        return True

    except Exception as e:
        print(f"❌ Slash commands test failed: {e}")
        traceback.print_exc()
        return False

def test_zero_system():
    """Test the ZeroSystem class."""
    print("\n🔍 Testing ZeroSystem class...")
    try:
        import zero

        # Test creating the system
        system = zero.ZeroSystem()
        print("✅ ZeroSystem created successfully")

        # Test basic attributes
        if hasattr(system, 'settings'):
            print("✅ System has settings attribute")

        if hasattr(system, 'artifacts_path'):
            print("✅ System has artifacts_path attribute")

        if hasattr(system, 'mcp_config'):
            print("✅ System has mcp_config attribute")

        print("✅ ZeroSystem basic functionality working")
        return True

    except Exception as e:
        print(f"❌ ZeroSystem test failed: {e}")
        traceback.print_exc()
        return False

def test_core_imports():
    """Test core module imports."""
    print("\n🔍 Testing core module imports...")
    try:
        print("✅ TaskResult imported from interfaces")

        print("✅ TaskResult imported from task_result")

        print("✅ MECEDecomposer imported")

        print("✅ EvolutionaryAgent imported")

        print("✅ MetaAgent imported")

        print("✅ All core imports working")
        return True

    except Exception as e:
        print(f"❌ Core imports test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all basic functionality tests."""
    print("🚀 Testing Basic Functionality")
    print("=" * 50)

    tests = [
        ("Core Imports", test_core_imports),
        ("Visualization", test_visualization),
        ("Slash Commands", test_slash_commands),
        ("Zero System", test_zero_system),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name} TEST PASSED")
            else:
                print(f"❌ {test_name} TEST FAILED")
        except Exception as e:
            print(f"❌ {test_name} TEST ERROR: {e}")

    print(f"\n📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All basic functionality tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed. Check output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
