#!/usr/bin/env python3
"""
MASTER CONTROL PROGRAM - COMPREHENSIVE VALIDATION

This script validates that all EvolutionaryAgent fixes are working correctly
and that the system can now operate without the abstract method error.
"""

import sys
import asyncio
import traceback
from pathlib import Path
from uuid import uuid4

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

class ValidationResult:
    """Holds results of validation tests."""
    def __init__(self, name: str, passed: bool, message: str = ""):
        self.name = name
        self.passed = passed
        self.message = message

class MasterControlProgram:
    """Master Control Program for comprehensive validation."""
    
    def __init__(self):
        self.results = []
        self.total_tests = 0
        self.passed_tests = 0
    
    def add_result(self, result: ValidationResult):
        """Add a test result."""
        self.results.append(result)
        self.total_tests += 1
        if result.passed:
            self.passed_tests += 1
    
    def test_critical_imports(self):
        """Test all critical imports that were previously failing."""
        print("🔍 Testing critical imports...")
        try:
            # Test UUID import (was failing)
            from uuid import UUID, uuid4
            
            # Test core imports
            from src.agents.evolutionary_agent import EvolutionaryAgent
            from src.core.interfaces import AgentRole, Task, TaskContext, Artifact, ArtifactType
            from src.core.result import Result
            from src.core.task_result import TaskResult
            from src.core.exceptions import TaskExecutionError
            
            # Test zero imports
            from zero import ZeroSystem
            
            self.add_result(ValidationResult("Critical Imports", True, "All imports successful"))
            print("✅ All critical imports successful")
            
        except Exception as e:
            self.add_result(ValidationResult("Critical Imports", False, f"Import failed: {e}"))
            print(f"❌ Import failed: {e}")
            traceback.print_exc()
    
    def test_evolutionary_agent_creation(self):
        """Test that EvolutionaryAgent can be created without abstract method error."""
        print("\n🔍 Testing EvolutionaryAgent creation...")
        try:
            from src.agents.evolutionary_agent import EvolutionaryAgent
            from src.core.interfaces import AgentRole
            
            # This should NOT raise: TypeError: Can't instantiate abstract class EvolutionaryAgent
            agent = EvolutionaryAgent(
                agent_id=uuid4(),
                role=AgentRole.CORE_LOGIC,
                artifact_storage_path=Path("./projects"),
                evolution_enabled=True
            )
            
            self.add_result(ValidationResult("EvolutionaryAgent Creation", True, "Agent created successfully"))
            print("✅ EvolutionaryAgent created successfully")
            
        except TypeError as e:
            if "Can't instantiate abstract class" in str(e):
                self.add_result(ValidationResult("EvolutionaryAgent Creation", False, f"CRITICAL: Abstract class error still present: {e}"))
                print(f"❌ CRITICAL: Abstract class error still present: {e}")
            else:
                self.add_result(ValidationResult("EvolutionaryAgent Creation", False, f"TypeError: {e}"))
                print(f"❌ TypeError: {e}")
        except Exception as e:
            self.add_result(ValidationResult("EvolutionaryAgent Creation", False, f"Unexpected error: {e}"))
            print(f"❌ Unexpected error: {e}")
            traceback.print_exc()
    
    def test_abstract_method_implementation(self):
        """Test that the abstract method is properly implemented."""
        print("\n🔍 Testing abstract method implementation...")
        try:
            from src.agents.evolutionary_agent import EvolutionaryAgent
            from src.core.interfaces import AgentRole
            
            agent = EvolutionaryAgent(
                agent_id=uuid4(),
                role=AgentRole.CORE_LOGIC,
                artifact_storage_path=Path("./projects"),
                evolution_enabled=True
            )
            
            # Test method exists
            if not hasattr(agent, '_execute_specific_task'):
                self.add_result(ValidationResult("Abstract Method", False, "Method _execute_specific_task does not exist"))
                print("❌ Method _execute_specific_task does not exist")
                return
            
            # Test method is callable
            if not callable(agent._execute_specific_task):
                self.add_result(ValidationResult("Abstract Method", False, "Method _execute_specific_task is not callable"))
                print("❌ Method _execute_specific_task is not callable")
                return
            
            # Test method is async
            import inspect
            if not inspect.iscoroutinefunction(agent._execute_specific_task):
                self.add_result(ValidationResult("Abstract Method", False, "Method _execute_specific_task is not async"))
                print("❌ Method _execute_specific_task is not async")
                return
            
            # Test method signature
            sig = inspect.signature(agent._execute_specific_task)
            params = list(sig.parameters.keys())
            expected_params = ['task', 'context']
            if params != expected_params:
                self.add_result(ValidationResult("Abstract Method", False, f"Wrong method signature: expected {expected_params}, got {params}"))
                print(f"❌ Wrong method signature: expected {expected_params}, got {params}")
                return
            
            self.add_result(ValidationResult("Abstract Method", True, "Method properly implemented"))
            print("✅ Abstract method properly implemented")
            
        except Exception as e:
            self.add_result(ValidationResult("Abstract Method", False, f"Error: {e}"))
            print(f"❌ Error testing abstract method: {e}")
            traceback.print_exc()
    
    async def test_zero_system_integration(self):
        """Test that ZeroSystem can now initialize with EvolutionaryAgent."""
        print("\n🔍 Testing ZeroSystem integration...")
        try:
            from zero import ZeroSystem
            
            # Create system
            system = ZeroSystem()
            
            # This should NOT fail with abstract class error
            await system.initialize()
            
            # Test evolution agent was created
            if not hasattr(system, 'evolution_agent'):
                self.add_result(ValidationResult("ZeroSystem Integration", False, "Evolution agent not created"))
                print("❌ Evolution agent not created")
                return
            
            if system.evolution_agent is None:
                self.add_result(ValidationResult("ZeroSystem Integration", False, "Evolution agent is None"))
                print("❌ Evolution agent is None")
                return
            
            # Clean shutdown
            await system.shutdown()
            
            self.add_result(ValidationResult("ZeroSystem Integration", True, "System integration successful"))
            print("✅ ZeroSystem integration successful")
            
        except Exception as e:
            self.add_result(ValidationResult("ZeroSystem Integration", False, f"Error: {e}"))
            print(f"❌ ZeroSystem integration failed: {e}")
            traceback.print_exc()
    
    def test_no_regression_errors(self):
        """Test that we haven't introduced any regression errors."""
        print("\n🔍 Testing for regression errors...")
        try:
            from src.agents.evolutionary_agent import EvolutionaryAgent
            from src.core.interfaces import AgentRole
            
            agent = EvolutionaryAgent(
                agent_id=uuid4(),
                role=AgentRole.CORE_LOGIC,
                artifact_storage_path=Path("./projects"),
                evolution_enabled=True
            )
            
            # Test that evolution-specific attributes exist
            required_attrs = ['memory', 'evolution_engine', 'evolution_enabled', 'task_history']
            for attr in required_attrs:
                if not hasattr(agent, attr):
                    self.add_result(ValidationResult("No Regression", False, f"Missing attribute: {attr}"))
                    print(f"❌ Missing attribute: {attr}")
                    return
            
            # Test that methods exist
            required_methods = ['get_performance_metrics', '_calculate_fitness', '_apply_patterns']
            for method in required_methods:
                if not hasattr(agent, method):
                    self.add_result(ValidationResult("No Regression", False, f"Missing method: {method}"))
                    print(f"❌ Missing method: {method}")
                    return
            
            self.add_result(ValidationResult("No Regression", True, "No regression errors found"))
            print("✅ No regression errors found")
            
        except Exception as e:
            self.add_result(ValidationResult("No Regression", False, f"Error: {e}"))
            print(f"❌ Regression test failed: {e}")
            traceback.print_exc()
    
    async def run_comprehensive_validation(self):
        """Run all validation tests."""
        print("🚀 MASTER CONTROL PROGRAM - COMPREHENSIVE VALIDATION")
        print("=" * 70)
        print("Validating all EvolutionaryAgent fixes...")
        print("=" * 70)
        
        # Run all tests
        self.test_critical_imports()
        self.test_evolutionary_agent_creation()
        self.test_abstract_method_implementation()
        await self.test_zero_system_integration()
        self.test_no_regression_errors()
        
        # Report results
        print("\n" + "=" * 70)
        print("📊 VALIDATION RESULTS")
        print("=" * 70)
        
        for result in self.results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            print(f"{status} {result.name}: {result.message}")
        
        print("\n" + "=" * 70)
        print(f"📈 SUMMARY: {self.passed_tests}/{self.total_tests} tests passed")
        print("=" * 70)
        
        if self.passed_tests == self.total_tests:
            print("🎉 ALL VALIDATION TESTS PASSED!")
            print("\n✅ EvolutionaryAgent fix is COMPLETE and working correctly:")
            print("  • No more 'Can't instantiate abstract class' errors")
            print("  • All imports are working")
            print("  • Abstract method '_execute_specific_task' is implemented")
            print("  • Constructor signature is correct")
            print("  • ZeroSystem integration is working")
            print("  • No regression errors introduced")
            print("\n🚀 The system is now ready for use!")
            return True
        else:
            print("⚠️  VALIDATION FAILED - Some tests did not pass.")
            print("\n❌ Issues found:")
            for result in self.results:
                if not result.passed:
                    print(f"  • {result.name}: {result.message}")
            return False

async def main():
    """Main validation function."""
    mcp = MasterControlProgram()
    success = await mcp.run_comprehensive_validation()
    return success

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)