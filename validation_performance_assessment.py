#!/usr/bin/env python3
"""
Master Control Program: Performance Impact Assessment

This test validates that the observability infrastructure meets the <5% overhead requirement:
- Baseline performance without monitoring
- Performance with full observability stack
- Memory usage impact analysis
- MCP event processing overhead
- Real-time metrics collection impact
"""

import asyncio
import sys
import time
import psutil
import statistics
from pathlib import Path
from typing import Dict, Any, List
import gc

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

import structlog
from src.utils.observability_init import initialize_observability, get_health_status
from src.core.mcp_events import initialize_mcp_events, emit_mcp_event, get_mcp_event_bus
from src.core.mcp_events import MCPEvent, MCPEventType, MCPEventSeverity
from src.utils.metrics import get_metrics
from config.settings import get_settings

logger = structlog.get_logger(__name__)


class PerformanceAssessmentTest:
    """Performance impact assessment for observability infrastructure."""
    
    def __init__(self):
        self.results = {}
        self.baseline_measurements = {}
        self.monitored_measurements = {}
        self.process = psutil.Process()
        
    async def run_assessment(self) -> Dict[str, Any]:
        """Run complete performance impact assessment."""
        
        print("⚡ MASTER CONTROL PROGRAM: PERFORMANCE IMPACT ASSESSMENT")
        print("=" * 70)
        print("Target: <5% monitoring overhead for production readiness")
        print("=" * 70)
        
        # Test baseline performance (no monitoring)
        await self._test_baseline_performance()
        
        # Initialize monitoring stack
        await self._initialize_monitoring_stack()
        
        # Test performance with monitoring
        await self._test_monitored_performance()
        
        # Test memory impact
        await self._test_memory_impact()
        
        # Test event processing overhead
        await self._test_event_processing_overhead()
        
        # Test high-frequency metrics overhead
        await self._test_metrics_overhead()
        
        # Calculate final impact assessment
        await self._calculate_performance_impact()
        
        return self._generate_report()
    
    async def _test_baseline_performance(self):
        """Test baseline performance without monitoring."""
        print("📊 Testing baseline performance (no monitoring)...")
        
        try:
            # Force garbage collection for clean measurement
            gc.collect()
            
            # Measure initial memory
            initial_memory = self.process.memory_info().rss
            
            # Run baseline workload multiple times
            baseline_times = []
            baseline_cpu_times = []
            
            for i in range(10):
                # Measure CPU time before
                cpu_before = self.process.cpu_times().user
                start_time = time.perf_counter()
                
                # Baseline workload: computational tasks without monitoring
                await self._baseline_workload()
                
                # Measure completion
                end_time = time.perf_counter()
                cpu_after = self.process.cpu_times().user
                
                baseline_times.append(end_time - start_time)
                baseline_cpu_times.append(cpu_after - cpu_before)
            
            # Measure final memory
            final_memory = self.process.memory_info().rss
            
            self.baseline_measurements = {
                "execution_times": baseline_times,
                "avg_execution_time": statistics.mean(baseline_times),
                "std_execution_time": statistics.stdev(baseline_times) if len(baseline_times) > 1 else 0,
                "cpu_times": baseline_cpu_times,
                "avg_cpu_time": statistics.mean(baseline_cpu_times),
                "initial_memory_mb": initial_memory / 1024 / 1024,
                "final_memory_mb": final_memory / 1024 / 1024,
                "memory_usage_mb": (final_memory - initial_memory) / 1024 / 1024
            }
            
            self.results["baseline_performance"] = {
                "status": "PASS",
                "measurements": self.baseline_measurements,
                "stable_timing": self.baseline_measurements["std_execution_time"] < 0.1,
                "baseline_established": True
            }
            
            print(f"✅ Baseline Performance: {self.baseline_measurements['avg_execution_time']:.3f}s avg")
            
        except Exception as e:
            self.results["baseline_performance"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Baseline Performance: FAIL - {e}")
    
    async def _initialize_monitoring_stack(self):
        """Initialize full monitoring stack."""
        print("🔧 Initializing monitoring stack...")
        
        try:
            # Initialize observability
            self.observability_manager = initialize_observability()
            
            # Initialize MCP events
            self.event_bus = await initialize_mcp_events()
            
            # Get metrics instance
            self.metrics = get_metrics()
            
            # Allow systems to stabilize
            await asyncio.sleep(0.5)
            
            print("✅ Monitoring stack initialized")
            
        except Exception as e:
            print(f"❌ Monitoring initialization failed: {e}")
            raise
    
    async def _test_monitored_performance(self):
        """Test performance with full monitoring."""
        print("📈 Testing performance with full monitoring...")
        
        try:
            # Force garbage collection for clean measurement
            gc.collect()
            
            # Measure initial memory
            initial_memory = self.process.memory_info().rss
            
            # Run monitored workload multiple times
            monitored_times = []
            monitored_cpu_times = []
            
            for i in range(10):
                # Measure CPU time before
                cpu_before = self.process.cpu_times().user
                start_time = time.perf_counter()
                
                # Monitored workload: same work + full observability
                await self._monitored_workload(i)
                
                # Measure completion
                end_time = time.perf_counter()
                cpu_after = self.process.cpu_times().user
                
                monitored_times.append(end_time - start_time)
                monitored_cpu_times.append(cpu_after - cpu_before)
            
            # Measure final memory
            final_memory = self.process.memory_info().rss
            
            self.monitored_measurements = {
                "execution_times": monitored_times,
                "avg_execution_time": statistics.mean(monitored_times),
                "std_execution_time": statistics.stdev(monitored_times) if len(monitored_times) > 1 else 0,
                "cpu_times": monitored_cpu_times,
                "avg_cpu_time": statistics.mean(monitored_cpu_times),
                "initial_memory_mb": initial_memory / 1024 / 1024,
                "final_memory_mb": final_memory / 1024 / 1024,
                "memory_usage_mb": (final_memory - initial_memory) / 1024 / 1024
            }
            
            self.results["monitored_performance"] = {
                "status": "PASS",
                "measurements": self.monitored_measurements,
                "stable_timing": self.monitored_measurements["std_execution_time"] < 0.1,
                "monitoring_functional": True
            }
            
            print(f"✅ Monitored Performance: {self.monitored_measurements['avg_execution_time']:.3f}s avg")
            
        except Exception as e:
            self.results["monitored_performance"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Monitored Performance: FAIL - {e}")
    
    async def _test_memory_impact(self):
        """Test memory usage impact of monitoring."""
        print("🧠 Testing memory impact...")
        
        try:
            # Get current process memory info
            memory_info = self.process.memory_info()
            
            # Get monitoring system memory usage
            event_bus_stats = self.event_bus.get_event_statistics()
            metrics_data_size = len(self.metrics.get_metrics_data())
            
            # Calculate memory overhead
            baseline_memory = self.baseline_measurements.get("memory_usage_mb", 0)
            monitored_memory = self.monitored_measurements.get("memory_usage_mb", 0)
            memory_overhead_mb = monitored_memory - baseline_memory
            
            # Calculate percentage overhead
            if baseline_memory > 0:
                memory_overhead_percent = (memory_overhead_mb / baseline_memory) * 100
            else:
                memory_overhead_percent = 0
            
            self.results["memory_impact"] = {
                "status": "PASS" if memory_overhead_percent < 10 else "WARN",
                "baseline_memory_mb": baseline_memory,
                "monitored_memory_mb": monitored_memory,
                "overhead_mb": memory_overhead_mb,
                "overhead_percent": memory_overhead_percent,
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "event_queue_size": event_bus_stats["queue_size"],
                "metrics_data_size": metrics_data_size
            }
            
            if memory_overhead_percent < 10:
                print(f"✅ Memory Impact: {memory_overhead_percent:.1f}% overhead")
            else:
                print(f"⚠️ Memory Impact: {memory_overhead_percent:.1f}% overhead (above 10%)")
            
        except Exception as e:
            self.results["memory_impact"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Memory Impact: FAIL - {e}")
    
    async def _test_event_processing_overhead(self):
        """Test MCP event processing overhead."""
        print("🔄 Testing event processing overhead...")
        
        try:
            # Test high-volume event processing
            start_time = time.perf_counter()
            cpu_before = self.process.cpu_times().user
            
            # Emit many events rapidly
            event_count = 1000
            for i in range(event_count):
                await emit_mcp_event(MCPEvent(
                    event_type=MCPEventType.TOOL_CALL_COMPLETED,
                    severity=MCPEventSeverity.DEBUG,
                    source="performance_test",
                    tool_name=f"test_tool_{i % 10}",
                    duration_ms=1.0,
                    data={"iteration": i, "batch": "performance"}
                ))
            
            # Allow processing to complete
            await asyncio.sleep(0.5)
            
            end_time = time.perf_counter()
            cpu_after = self.process.cpu_times().user
            
            # Calculate processing metrics
            total_time = end_time - start_time
            cpu_time = cpu_after - cpu_before
            events_per_second = event_count / total_time
            avg_processing_time_ms = (total_time / event_count) * 1000
            
            # Check final event statistics
            final_stats = self.event_bus.get_event_statistics()
            
            self.results["event_processing_overhead"] = {
                "status": "PASS" if events_per_second > 500 else "WARN",
                "events_emitted": event_count,
                "total_time_seconds": total_time,
                "cpu_time_seconds": cpu_time,
                "events_per_second": events_per_second,
                "avg_processing_time_ms": avg_processing_time_ms,
                "final_queue_size": final_stats["queue_size"],
                "total_events_processed": final_stats["total_events"],
                "processing_efficient": events_per_second > 500
            }
            
            if events_per_second > 500:
                print(f"✅ Event Processing: {events_per_second:.0f} events/sec")
            else:
                print(f"⚠️ Event Processing: {events_per_second:.0f} events/sec (below 500)")
            
        except Exception as e:
            self.results["event_processing_overhead"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Event Processing Overhead: FAIL - {e}")
    
    async def _test_metrics_overhead(self):
        """Test metrics collection overhead."""
        print("📊 Testing metrics collection overhead...")
        
        try:
            # Test high-frequency metrics collection
            start_time = time.perf_counter()
            cpu_before = self.process.cpu_times().user
            
            # Record many metrics rapidly
            metric_operations = 1000
            for i in range(metric_operations):
                # Counter increments
                self.metrics.task_total.labels(
                    status="success", agent_role="perf_test", task_type="counter"
                ).inc()
                
                # Histogram observations
                self.metrics.task_duration.labels(
                    agent_role="perf_test", task_type="histogram"
                ).observe(0.001)
                
                # Gauge updates
                self.metrics.task_queue_size.labels(priority="high").set(i % 100)
                
                # API metrics
                self.metrics.api_requests.labels(
                    service="test", endpoint="perf", status="200"
                ).inc()
            
            end_time = time.perf_counter()
            cpu_after = self.process.cpu_times().user
            
            # Calculate metrics overhead
            total_time = end_time - start_time
            cpu_time = cpu_after - cpu_before
            operations_per_second = metric_operations / total_time
            avg_operation_time_ms = (total_time / metric_operations) * 1000
            
            # Get final metrics data size
            metrics_data = self.metrics.get_metrics_data()
            
            self.results["metrics_overhead"] = {
                "status": "PASS" if operations_per_second > 1000 else "WARN",
                "operations_performed": metric_operations,
                "total_time_seconds": total_time,
                "cpu_time_seconds": cpu_time,
                "operations_per_second": operations_per_second,
                "avg_operation_time_ms": avg_operation_time_ms,
                "metrics_data_size_bytes": len(metrics_data),
                "collection_efficient": operations_per_second > 1000
            }
            
            if operations_per_second > 1000:
                print(f"✅ Metrics Overhead: {operations_per_second:.0f} ops/sec")
            else:
                print(f"⚠️ Metrics Overhead: {operations_per_second:.0f} ops/sec (below 1000)")
            
        except Exception as e:
            self.results["metrics_overhead"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Metrics Overhead: FAIL - {e}")
    
    async def _calculate_performance_impact(self):
        """Calculate overall performance impact."""
        print("🎯 Calculating overall performance impact...")
        
        try:
            # Calculate execution time overhead
            baseline_time = self.baseline_measurements["avg_execution_time"]
            monitored_time = self.monitored_measurements["avg_execution_time"]
            
            time_overhead_seconds = monitored_time - baseline_time
            time_overhead_percent = (time_overhead_seconds / baseline_time) * 100
            
            # Calculate CPU overhead
            baseline_cpu = self.baseline_measurements["avg_cpu_time"]
            monitored_cpu = self.monitored_measurements["avg_cpu_time"]
            
            cpu_overhead_seconds = monitored_cpu - baseline_cpu
            cpu_overhead_percent = (cpu_overhead_seconds / baseline_cpu) * 100 if baseline_cpu > 0 else 0
            
            # Get memory overhead from previous test
            memory_overhead_percent = self.results["memory_impact"]["overhead_percent"]
            
            # Determine overall status
            # Production target: <5% overhead
            # Warning threshold: <10% overhead
            max_overhead = max(time_overhead_percent, cpu_overhead_percent, memory_overhead_percent)
            
            if max_overhead < 5:
                overall_status = "PASS"
            elif max_overhead < 10:
                overall_status = "PASS_WITH_WARNINGS"
            else:
                overall_status = "FAIL"
            
            self.results["performance_impact"] = {
                "status": overall_status,
                "baseline_execution_time": baseline_time,
                "monitored_execution_time": monitored_time,
                "time_overhead_seconds": time_overhead_seconds,
                "time_overhead_percent": time_overhead_percent,
                "baseline_cpu_time": baseline_cpu,
                "monitored_cpu_time": monitored_cpu,
                "cpu_overhead_seconds": cpu_overhead_seconds,
                "cpu_overhead_percent": cpu_overhead_percent,
                "memory_overhead_percent": memory_overhead_percent,
                "max_overhead_percent": max_overhead,
                "meets_production_target": max_overhead < 5,
                "meets_warning_threshold": max_overhead < 10
            }
            
            if overall_status == "PASS":
                print(f"✅ Performance Impact: {max_overhead:.1f}% max overhead (meets <5% target)")
            elif overall_status == "PASS_WITH_WARNINGS":
                print(f"⚠️ Performance Impact: {max_overhead:.1f}% max overhead (above 5% target)")
            else:
                print(f"❌ Performance Impact: {max_overhead:.1f}% max overhead (above 10% threshold)")
            
        except Exception as e:
            self.results["performance_impact"] = {
                "status": "FAIL",
                "error": str(e)
            }
            print(f"❌ Performance Impact Calculation: FAIL - {e}")
    
    async def _baseline_workload(self):
        """Baseline computational workload without monitoring."""
        # Computational tasks that represent typical agent work
        data = list(range(1000))
        
        # Simulate data processing
        processed = [x * x for x in data if x % 2 == 0]
        
        # Simulate I/O-like operations
        await asyncio.sleep(0.01)
        
        # More computation
        result = sum(processed) / len(processed) if processed else 0
        
        return result
    
    async def _monitored_workload(self, iteration: int):
        """Same workload but with full monitoring."""
        # Start task tracking
        logger.info("Starting monitored workload", iteration=iteration, workload_type="performance_test")
        
        # Emit start event
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.AGENT_TASK_STARTED,
            severity=MCPEventSeverity.DEBUG,
            source="performance_test",
            data={"iteration": iteration, "workload": "monitored"}
        ))
        
        # Record metrics
        self.metrics.task_total.labels(status="started", agent_role="performance", task_type="workload").inc()
        
        # Same computational work as baseline
        start_time = time.perf_counter()
        
        data = list(range(1000))
        processed = [x * x for x in data if x % 2 == 0]
        await asyncio.sleep(0.01)
        result = sum(processed) / len(processed) if processed else 0
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        
        # Record completion metrics
        self.metrics.task_total.labels(status="success", agent_role="performance", task_type="workload").inc()
        self.metrics.task_duration.labels(agent_role="performance", task_type="workload").observe(duration)
        
        # Emit completion event
        await emit_mcp_event(MCPEvent(
            event_type=MCPEventType.AGENT_TASK_COMPLETED,
            severity=MCPEventSeverity.DEBUG,
            source="performance_test",
            duration_ms=duration * 1000,
            data={"iteration": iteration, "workload": "monitored", "result": result}
        ))
        
        # Log completion
        logger.info("Completed monitored workload", iteration=iteration, duration_ms=duration * 1000)
        
        return result
    
    def _generate_report(self) -> Dict[str, Any]:
        """Generate final performance assessment report."""
        print("\n" + "=" * 70)
        print("⚡ PERFORMANCE IMPACT ASSESSMENT REPORT")
        print("=" * 70)
        
        # Count results
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results.values() if r["status"] == "PASS")
        warned_tests = sum(1 for r in self.results.values() if r["status"] == "PASS_WITH_WARNINGS")
        failed_tests = sum(1 for r in self.results.values() if r["status"] == "FAIL")
        
        # Overall status
        if failed_tests == 0 and warned_tests == 0:
            overall_status = "PASS"
        elif failed_tests == 0:
            overall_status = "PASS_WITH_WARNINGS"
        else:
            overall_status = "FAIL"
        
        # Print detailed performance results
        if "performance_impact" in self.results:
            impact = self.results["performance_impact"]
            print(f"📊 PERFORMANCE OVERHEAD ANALYSIS:")
            print(f"   Time Overhead: {impact.get('time_overhead_percent', 0):.2f}%")
            print(f"   CPU Overhead: {impact.get('cpu_overhead_percent', 0):.2f}%")
            print(f"   Memory Overhead: {impact.get('memory_overhead_percent', 0):.2f}%")
            print(f"   Maximum Overhead: {impact.get('max_overhead_percent', 0):.2f}%")
            print(f"   Production Target (<5%): {'✅' if impact.get('meets_production_target', False) else '❌'}")
        
        # Print summary
        print(f"\n📋 TEST RESULTS:")
        for test_name, result in self.results.items():
            status_emoji = {"PASS": "✅", "PASS_WITH_WARNINGS": "⚠️", "FAIL": "❌"}[result["status"]]
            print(f"{status_emoji} {test_name.replace('_', ' ').title()}: {result['status']}")
            
            if result["status"] == "FAIL":
                print(f"   Error: {result.get('error', 'Unknown error')}")
            elif result["status"] == "PASS_WITH_WARNINGS":
                print(f"   Warning: Performance above optimal thresholds")
        
        print(f"\n📊 SUMMARY: {passed_tests}/{total_tests} tests passed")
        if warned_tests > 0:
            print(f"⚠️  {warned_tests} warning(s)")
        if failed_tests > 0:
            print(f"❌ {failed_tests} failure(s)")
        
        print(f"\n🎯 OVERALL STATUS: {overall_status}")
        
        if overall_status == "PASS":
            print(f"\n🏆 PERFORMANCE TARGET ACHIEVED!")
            print(f"✅ Observability infrastructure meets <5% overhead requirement")
            print(f"✅ System ready for production deployment")
        elif overall_status == "PASS_WITH_WARNINGS":
            print(f"\n⚠️ PERFORMANCE ACCEPTABLE WITH WARNINGS")
            print(f"⚠️ Observability overhead above 5% but below 10%")
            print(f"💡 Consider optimization for production")
        else:
            print(f"\n❌ PERFORMANCE TARGET NOT MET")
            print(f"❌ Observability overhead above 10% threshold")
            print(f"🔧 Optimization required before production")
        
        return {
            "overall_status": overall_status,
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "warned_tests": warned_tests,
            "failed_tests": failed_tests,
            "performance_overhead": self.results.get("performance_impact", {}),
            "detailed_results": self.results
        }


async def main():
    """Run performance impact assessment."""
    assessor = PerformanceAssessmentTest()
    report = await assessor.run_assessment()
    
    # Return appropriate exit code
    if report["overall_status"] == "FAIL":
        sys.exit(1)
    elif report["overall_status"] == "PASS_WITH_WARNINGS":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())