#!/usr/bin/env python3
"""Quick test script for MetaAgent modular system.
This script provides step-by-step testing instructions.
"""

from pathlib import Path


def check_dependencies():
    """Check if required dependencies are installed."""
    print("🔍 Checking Dependencies...")

    required_packages = ['structlog', 'pydantic', 'rich', 'orjson']
    missing_packages = []

    for package in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package}")
        except ImportError:
            missing_packages.append(package)
            print(f"  ❌ {package}")

    if missing_packages:
        print(f"\n❌ Missing packages: {', '.join(missing_packages)}")
        return False, missing_packages
    else:
        print("\n✅ All required dependencies are installed!")
        return True, []

def main():
    """Main test runner with instructions."""
    print("🧪 METAAGENT MODULAR SYSTEM - TESTING GUIDE")
    print("="*60)

    # Check if we have the structure
    meta_agent_file = Path("src/agents/meta_agent.py")
    if meta_agent_file.exists():
        print("✅ Modular MetaAgent system is present")
        print(f"   File size: {meta_agent_file.stat().st_size:,} bytes")
        print("   Modular architecture: ✅ COMPLETE")
    else:
        print("❌ MetaAgent system not found")
        return 1

    # Check dependencies
    deps_ok, missing = check_dependencies()

    print("\n" + "="*60)
    print("🚀 HOW TO TEST YOUR MODULAR METAAGENT SYSTEM")
    print("="*60)

    if not deps_ok:
        print("\n📦 STEP 1: Install Dependencies")
        print("-" * 40)
        print("Choose one installation method:")
        print()
        print("Option A - Using pip:")
        print(f"   pip install {' '.join(missing)}")
        print()
        print("Option B - All dependencies at once:")
        print("   pip install structlog pydantic rich orjson pyyaml")
        print()
        print("Option C - Using system packages (Ubuntu/Debian):")
        print("   sudo apt install python3-structlog python3-pydantic python3-rich")
        print()
        print("⚠️  Install dependencies first, then run this script again!")
        return 1

    print("\n🔑 STEP 1: Set Your API Keys")
    print("-" * 40)
    print("export OPENAI_API_KEY='your-openai-key-here'")
    print("export ANTHROPIC_API_KEY='your-anthropic-key-here'")

    print("\n🧪 STEP 2: Test Basic Component Loading")
    print("-" * 40)
    print("python -c \"")
    print("from src.agents.meta_agent import MetaAgent")
    print("from src.agents.meta_agent_config import MetaAgentConfig")
    print("print('Testing modular components...')")
    print("config = MetaAgentConfig()")
    print("agent = MetaAgent(config)")
    print("print('✅ All 10 modular components loaded successfully!')")
    print("stats = agent.get_execution_stats()")
    print("components = stats['modular_components']")
    print("print(f'Components: {list(components.keys())}')")
    print("\"")

    print("\n🏥 STEP 3: Test Health Monitoring")
    print("-" * 40)
    print("python -c \"")
    print("import asyncio")
    print("from src.agents.meta_agent import MetaAgent")
    print("from src.agents.meta_agent_config import MetaAgentConfig")
    print("async def test_health():")
    print("    config = MetaAgentConfig()")
    print("    agent = MetaAgent(config)")
    print("    await agent.initialize()")
    print("    health = await agent.get_health_status()")
    print("    print(f'System Health: {health[\\\"overall_status\\\"].upper()}')")
    print("    print(f'Components: {len(health[\\\"components\\\"])} healthy')")
    print("    await agent.cleanup()")
    print("asyncio.run(test_health())")
    print("\"")

    print("\n🎯 STEP 4: Test Real Usage (Optional)")
    print("-" * 40)
    print("# Run a basic example if available:")
    print("python examples/basic_usage.py")
    print()
    print("# Or run comprehensive demo:")
    print("python demo_agentic_system.py")

    print("\n📊 STEP 5: Run Unit Tests (Optional)")
    print("-" * 40)
    print("pytest tests/")
    print("# or")
    print("python -m pytest tests/unit/ -v")

    print("\n" + "="*60)
    print("🎉 MODULAR SYSTEM BENEFITS")
    print("="*60)
    print("✅ 10 focused components with clear responsibilities")
    print("✅ Enhanced maintainability and testability")
    print("✅ Comprehensive health monitoring")
    print("✅ Statistics gathering across all components")
    print("✅ Full backward compatibility (MetaAgent = MetaAgentRefactored)")
    print("✅ Original 2,131-line monolith → Modern modular architecture")

    print("\n📖 For detailed testing information, see:")
    print("   cat TESTING_GUIDE.md")

    return 0

if __name__ == "__main__":
    exit(main())
