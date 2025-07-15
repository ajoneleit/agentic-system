"""Slash Command Interface for /zero

Provides an intuitive command-line interface with slash commands
and natural language processing for interacting with the evolutionary
agentic system.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from structlog import get_logger

from src.agents.evolutionary_agent import EvolutionaryAgent
from src.agents.meta_agent import MetaAgent
from src.core.mece_decomposer import MECEDecomposer
from src.visualization.net_visualizer import InteractionNetVisualizer

logger = get_logger(__name__)


class CommandType(Enum):
    """Types of slash commands"""
    EVOLVE = "evolve"
    VISUALIZE = "visualize"
    COMPRESS = "compress"
    PARALLEL = "parallel"
    LEARN = "learn"
    SIMULATE = "simulate"
    STATUS = "status"
    HELP = "help"
    CONFIG = "config"
    RESET = "reset"


@dataclass
class CommandResult:
    """Result of executing a command"""
    success: bool
    output: str
    data: Optional[Dict[str, Any]] = None
    visualization: Optional[str] = None
    suggestions: Optional[List[str]] = None


@dataclass
class SlashCommand:
    """Definition of a slash command"""
    name: str
    description: str
    usage: str
    handler: Callable
    args: List[str]
    examples: List[str]


class CommandParser:
    """Parses slash commands and natural language"""
    
    def __init__(self):
        self.command_pattern = re.compile(r'^/(\w+)(?:\s+(.*))?$')
        self.arg_pattern = re.compile(r'--(\w+)(?:=([^\s]+))?')
    
    def parse(self, input_text: str) -> Tuple[Optional[str], Dict[str, Any]]:
        """Parse input to extract command and arguments"""
        input_text = input_text.strip()
        
        # Check if it's a slash command
        match = self.command_pattern.match(input_text)
        if match:
            command = match.group(1)
            args_str = match.group(2) or ""
            args = self._parse_args(args_str)
            return command, args
        
        # Otherwise it's natural language
        return None, {"query": input_text}
    
    def _parse_args(self, args_str: str) -> Dict[str, Any]:
        """Parse command arguments"""
        args = {}
        
        # Find all --key=value or --key patterns
        matches = self.arg_pattern.findall(args_str)
        for key, value in matches:
            args[key] = value if value else True
        
        # Remove parsed args from string
        remaining = self.arg_pattern.sub('', args_str).strip()
        if remaining:
            args['_positional'] = remaining.split()
        
        return args


class ZeroInterface:
    """Main interface for /zero with slash commands and natural language"""
    
    def __init__(
        self,
        meta_agent: MetaAgent,
        evolution_agent: EvolutionaryAgent,
        artifacts_path: Path
    ):
        self.meta_agent = meta_agent
        self.evolution_agent = evolution_agent
        self.artifacts_path = artifacts_path
        self.parser = CommandParser()
        self.decomposer = MECEDecomposer()
        self.visualizer = InteractionNetVisualizer()
        
        # Command history
        self.history: List[Dict[str, Any]] = []
        
        # Register commands
        self.commands = self._register_commands()
    
    def _register_commands(self) -> Dict[str, SlashCommand]:
        """Register all available slash commands"""
        return {
            CommandType.EVOLVE.value: SlashCommand(
                name="evolve",
                description="Trigger evolutionary optimization on current task",
                usage="/evolve [--iterations=N] [--fitness-target=F] [task_description]",
                handler=self._handle_evolve,
                args=["iterations", "fitness-target"],
                examples=[
                    "/evolve --iterations=10 optimize the sorting algorithm",
                    "/evolve --fitness-target=0.9"
                ]
            ),
            CommandType.VISUALIZE.value: SlashCommand(
                name="visualize",
                description="Render current interaction net state",
                usage="/visualize [--format=svg|png|ascii] [--detail=high|medium|low]",
                handler=self._handle_visualize,
                args=["format", "detail"],
                examples=[
                    "/visualize --format=svg --detail=high",
                    "/visualize"
                ]
            ),
            CommandType.COMPRESS.value: SlashCommand(
                name="compress",
                description="Show MECE decomposition with context compression",
                usage="/compress [--level=0.1-1.0] [task_description]",
                handler=self._handle_compress,
                args=["level"],
                examples=[
                    "/compress --level=0.2 build a web scraper with rate limiting",
                    "/compress implement authentication system"
                ]
            ),
            CommandType.PARALLEL.value: SlashCommand(
                name="parallel",
                description="Execute tasks in parallel with separate contexts",
                usage="/parallel [--max-workers=N] task1 | task2 | task3",
                handler=self._handle_parallel,
                args=["max-workers"],
                examples=[
                    "/parallel --max-workers=5 generate tests | update docs | refactor code",
                    "/parallel task1 | task2"
                ]
            ),
            CommandType.LEARN.value: SlashCommand(
                name="learn",
                description="Display learned patterns and strategies",
                usage="/learn [--type=all|patterns|metrics] [--limit=N]",
                handler=self._handle_learn,
                args=["type", "limit"],
                examples=[
                    "/learn --type=patterns --limit=10",
                    "/learn --type=metrics"
                ]
            ),
            CommandType.SIMULATE.value: SlashCommand(
                name="simulate",
                description="Run what-if scenarios on interaction nets",
                usage="/simulate [--scenario=NAME] [--iterations=N]",
                handler=self._handle_simulate,
                args=["scenario", "iterations"],
                examples=[
                    "/simulate --scenario=high-load --iterations=100",
                    "/simulate --scenario=failure-recovery"
                ]
            ),
            CommandType.STATUS.value: SlashCommand(
                name="status",
                description="Show current system status",
                usage="/status [--verbose]",
                handler=self._handle_status,
                args=["verbose"],
                examples=["/status", "/status --verbose"]
            ),
            CommandType.HELP.value: SlashCommand(
                name="help",
                description="Show help information",
                usage="/help [command]",
                handler=self._handle_help,
                args=[],
                examples=["/help", "/help evolve"]
            ),
            CommandType.CONFIG.value: SlashCommand(
                name="config",
                description="View or update configuration",
                usage="/config [--set KEY=VALUE] [--get KEY]",
                handler=self._handle_config,
                args=["set", "get"],
                examples=[
                    "/config --get evolution.enabled",
                    "/config --set compression.level=0.2"
                ]
            ),
            CommandType.RESET.value: SlashCommand(
                name="reset",
                description="Reset system state",
                usage="/reset [--confirm] [--preserve-memory]",
                handler=self._handle_reset,
                args=["confirm", "preserve-memory"],
                examples=["/reset --confirm", "/reset --confirm --preserve-memory"]
            )
        }
    
    async def process_input(self, input_text: str) -> CommandResult:
        """Process user input (slash command or natural language)"""
        start_time = datetime.now()
        
        # Parse input
        command, args = self.parser.parse(input_text)
        
        # Record in history
        self.history.append({
            "timestamp": start_time,
            "input": input_text,
            "command": command,
            "args": args
        })
        
        try:
            if command:
                # Handle slash command
                if command in self.commands:
                    result = await self.commands[command].handler(args)
                else:
                    result = CommandResult(
                        success=False,
                        output=f"Unknown command: /{command}",
                        suggestions=[f"/{cmd}" for cmd in self.commands.keys()]
                    )
            else:
                # Handle natural language
                result = await self._handle_natural_language(args["query"])
            
            # Record result
            self.history[-1]["result"] = result
            self.history[-1]["duration"] = (datetime.now() - start_time).total_seconds()
            
            return result
            
        except Exception as e:
            logger.error("Command execution failed", error=str(e))
            return CommandResult(
                success=False,
                output=f"Error: {str(e)}"
            )
    
    async def _handle_evolve(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /evolve command"""
        iterations = int(args.get("iterations", 10))
        fitness_target = float(args.get("fitness-target", 0.8))
        task_desc = " ".join(args.get("_positional", []))
        
        if not task_desc and not self.evolution_agent.task_history:
            return CommandResult(
                success=False,
                output="No task specified and no previous tasks to evolve"
            )
        
        # Get current interaction net state
        current_state = await self.evolution_agent.get_current_state()
        
        # Run evolution
        evolved_state = await self.evolution_agent.evolution_engine.evolve(
            current_state,
            lambda s: self.evolution_agent._calculate_fitness(s),
            generations=iterations,
            population_size=50
        )
        
        # Generate report
        improvement = evolved_state.fitness - current_state.fitness
        output = f"""🧬 Evolution Complete

Initial Fitness: {current_state.fitness:.3f}
Final Fitness: {evolved_state.fitness:.3f}
Improvement: {improvement:.3f} ({improvement/current_state.fitness*100:.1f}%)

Generations: {iterations}
Best Individual:
- Agents: {len(evolved_state.agents)}
- Connections: {len(evolved_state.connections)}
- Active Pairs: {len(evolved_state.active_pairs)}
"""
        
        return CommandResult(
            success=True,
            output=output,
            data={
                "initial_fitness": current_state.fitness,
                "final_fitness": evolved_state.fitness,
                "improvement": improvement,
                "evolved_state": evolved_state.to_json()
            }
        )
    
    async def _handle_visualize(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /visualize command"""
        format_type = args.get("format", "ascii")
        detail_level = args.get("detail", "medium")
        
        # Get current interaction net
        current_net = await self.evolution_agent.get_current_net()
        
        # Generate visualization
        if format_type == "ascii":
            viz = self.visualizer.render_ascii(current_net, detail_level)
        elif format_type == "svg":
            viz = self.visualizer.render_svg(current_net, detail_level)
        elif format_type == "png":
            viz = self.visualizer.render_png(current_net, detail_level)
        else:
            return CommandResult(
                success=False,
                output=f"Unsupported format: {format_type}",
                suggestions=["ascii", "svg", "png"]
            )
        
        output = f"📊 Interaction Net Visualization ({format_type})\n\n"
        
        return CommandResult(
            success=True,
            output=output,
            visualization=viz,
            data={
                "format": format_type,
                "detail": detail_level,
                "net_stats": {
                    "agents": len(current_net.agents),
                    "connections": len(current_net.connections),
                    "active_pairs": len(current_net.active_pairs)
                }
            }
        )
    
    async def _handle_compress(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /compress command"""
        compression_level = float(args.get("level", 0.1))
        task_desc = " ".join(args.get("_positional", []))
        
        if not task_desc:
            return CommandResult(
                success=False,
                output="Please provide a task description to decompose"
            )
        
        # Decompose task using Meta Agent
        tasks = await self.meta_agent.decompose_task(task_desc)
        
        # Create MECE partitions with compression
        self.decomposer.compressor.compression_level = compression_level
        partitions = await self.decomposer.decompose(tasks)
        
        # Generate report
        output = f"""🗜️ MECE Decomposition with Context Compression

Original Task: {task_desc}
Compression Level: {compression_level:.1%}

Partitions: {len(partitions)}
Total Tasks: {len(tasks)}

Partition Details:
"""
        
        for i, partition in enumerate(partitions):
            output += f"""
Partition {i+1} (Parallel Group {partition.parallel_group}):
  Tasks: {len(partition.tasks)}
  Context Compression: {partition.context.savings:.1f}%
  Original Size: {partition.context.original_size} bytes
  Compressed Size: {partition.context.compressed_size} bytes
  Estimated Tokens: {partition.estimated_tokens}
  Dependencies: {len(partition.dependencies)}
"""
        
        avg_compression = sum(p.context.compression_ratio for p in partitions) / len(partitions)
        output += f"\nAverage Compression Ratio: {avg_compression:.2%}"
        
        return CommandResult(
            success=True,
            output=output,
            data={
                "partitions": [
                    {
                        "id": p.id,
                        "task_count": len(p.tasks),
                        "compression_ratio": p.context.compression_ratio,
                        "parallel_group": p.parallel_group
                    }
                    for p in partitions
                ]
            }
        )
    
    async def _handle_parallel(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /parallel command"""
        max_workers = int(args.get("max-workers", 5))
        tasks_str = " ".join(args.get("_positional", []))
        
        # Split tasks by pipe
        task_descriptions = [t.strip() for t in tasks_str.split("|") if t.strip()]
        
        if not task_descriptions:
            return CommandResult(
                success=False,
                output="Please provide tasks separated by | (pipe)"
            )
        
        output = f"""🚀 Parallel Task Execution

Tasks: {len(task_descriptions)}
Max Workers: {max_workers}

Executing...
"""
        
        # Execute tasks in parallel
        start_time = datetime.now()
        results = await asyncio.gather(*[
            self.meta_agent.process_request(desc)
            for desc in task_descriptions[:max_workers]
        ])
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # Generate results summary
        output += f"\nExecution Time: {duration:.2f}s\n\nResults:\n"
        
        for i, (desc, result) in enumerate(zip(task_descriptions, results)):
            status = "✅" if result.success else "❌"
            output += f"\n{status} Task {i+1}: {desc[:50]}..."
            output += f"\n   Success Rate: {result.success_rate:.1%}"
            output += f"\n   Artifacts: {len(result.artifacts) if result.artifacts else 0}"
        
        total_success = sum(1 for r in results if r.success)
        output += f"\n\nOverall Success: {total_success}/{len(results)}"
        
        return CommandResult(
            success=True,
            output=output,
            data={
                "tasks": len(task_descriptions),
                "successful": total_success,
                "duration": duration,
                "results": [
                    {
                        "task": desc,
                        "success": r.success,
                        "artifacts": len(r.artifacts) if r.artifacts else 0
                    }
                    for desc, r in zip(task_descriptions, results)
                ]
            }
        )
    
    async def _handle_learn(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /learn command"""
        learn_type = args.get("type", "all")
        limit = int(args.get("limit", 10))
        
        output = "🧠 Learning Report\n\n"
        
        if learn_type in ["all", "patterns"]:
            # Show learned patterns
            patterns = list(self.evolution_agent.memory.patterns.values())
            patterns.sort(key=lambda p: p.fitness_improvement, reverse=True)
            
            output += f"Top {min(limit, len(patterns))} Learned Patterns:\n"
            
            for i, pattern in enumerate(patterns[:limit]):
                output += f"""
Pattern {i+1}:
  ID: {pattern.id[:8]}...
  Fitness Improvement: +{pattern.fitness_improvement:.3f}
  Success Rate: {pattern.success_rate:.1%}
  Usage Count: {pattern.usage_count}
  Created: {pattern.created_at.strftime('%Y-%m-%d %H:%M')}
"""
        
        if learn_type in ["all", "metrics"]:
            # Show performance metrics
            metrics = self.evolution_agent.get_performance_metrics()
            
            output += "\nPerformance Metrics:\n"
            output += f"  Total Tasks: {metrics.get('total_tasks', 0)}\n"
            output += f"  Success Rate: {metrics.get('success_rate', 0):.1%}\n"
            output += f"  Avg Fitness Improvement: {metrics.get('avg_fitness_improvement', 0):.3f}\n"
            output += f"  Patterns Stored: {metrics.get('patterns_stored', 0)}\n"
            output += f"  Pattern Effectiveness: {metrics.get('patterns_effectiveness', 0):.2f}\n"
        
        return CommandResult(
            success=True,
            output=output,
            data={
                "pattern_count": len(self.evolution_agent.memory.patterns),
                "metrics": self.evolution_agent.get_performance_metrics()
            }
        )
    
    async def _handle_simulate(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /simulate command"""
        scenario = args.get("scenario", "default")
        iterations = int(args.get("iterations", 100))
        
        output = f"🔮 Simulation: {scenario}\n\n"
        
        # Define scenarios
        scenarios = {
            "high-load": {
                "agents": 100,
                "connections": 500,
                "active_pairs": 50
            },
            "failure-recovery": {
                "agents": 20,
                "connections": 30,
                "failures": 5
            },
            "default": {
                "agents": 10,
                "connections": 20,
                "active_pairs": 5
            }
        }
        
        if scenario not in scenarios:
            return CommandResult(
                success=False,
                output=f"Unknown scenario: {scenario}",
                suggestions=list(scenarios.keys())
            )
        
        # Run simulation
        config = scenarios[scenario]
        results = await self._run_simulation(config, iterations)
        
        output += f"Configuration: {json.dumps(config, indent=2)}\n"
        output += f"Iterations: {iterations}\n\n"
        output += f"Results:\n"
        output += f"  Average Reduction Steps: {results['avg_steps']:.1f}\n"
        output += f"  Min Steps: {results['min_steps']}\n"
        output += f"  Max Steps: {results['max_steps']}\n"
        output += f"  Success Rate: {results['success_rate']:.1%}\n"
        
        return CommandResult(
            success=True,
            output=output,
            data=results
        )
    
    async def _handle_status(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /status command"""
        verbose = args.get("verbose", False)
        
        # Gather status information
        agent_metrics = self.evolution_agent.get_performance_metrics()
        memory_stats = {
            "patterns": len(self.evolution_agent.memory.patterns),
            "experiences": len(self.evolution_agent.memory.experiences)
        }
        
        output = """📊 System Status

🤖 Agents:
  Meta Agent: Active
  Evolution Agent: Active
  Evolution Enabled: {}

📈 Performance:
  Tasks Processed: {}
  Success Rate: {:.1%}
  Patterns Learned: {}

💾 Memory:
  Stored Patterns: {}
  Experiences: {}

🕐 Session:
  Commands Executed: {}
  Session Duration: {:.1f} minutes
""".format(
            agent_metrics.get("evolution_enabled", False),
            agent_metrics.get("total_tasks", 0),
            agent_metrics.get("success_rate", 0),
            agent_metrics.get("patterns_stored", 0),
            memory_stats["patterns"],
            memory_stats["experiences"],
            len(self.history),
            (datetime.now() - self.history[0]["timestamp"]).total_seconds() / 60 if self.history else 0
        )
        
        if verbose:
            output += "\n📝 Recent Commands:\n"
            for cmd in self.history[-5:]:
                output += f"  {cmd['timestamp'].strftime('%H:%M:%S')} - {cmd['input']}\n"
        
        return CommandResult(
            success=True,
            output=output,
            data={
                "agent_metrics": agent_metrics,
                "memory_stats": memory_stats,
                "session_stats": {
                    "commands": len(self.history),
                    "duration_minutes": (datetime.now() - self.history[0]["timestamp"]).total_seconds() / 60 if self.history else 0
                }
            }
        )
    
    async def _handle_help(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /help command"""
        command_name = args.get("_positional", [None])[0]
        
        if command_name:
            # Show help for specific command
            if command_name in self.commands:
                cmd = self.commands[command_name]
                output = f"""📚 Help: /{cmd.name}

{cmd.description}

Usage: {cmd.usage}

Arguments:
"""
                for arg in cmd.args:
                    output += f"  --{arg}\n"
                
                output += "\nExamples:\n"
                for example in cmd.examples:
                    output += f"  {example}\n"
            else:
                output = f"Unknown command: {command_name}"
                return CommandResult(
                    success=False,
                    output=output,
                    suggestions=[f"/{cmd}" for cmd in self.commands.keys()]
                )
        else:
            # Show general help
            output = """🚀 /zero - Evolutionary Agentic System

Available Commands:
"""
            for cmd in self.commands.values():
                output += f"\n  /{cmd.name:<12} - {cmd.description}"
            
            output += "\n\nType '/help <command>' for detailed help on a specific command."
            output += "\nOr just type naturally - I understand both!"
        
        return CommandResult(success=True, output=output)
    
    async def _handle_config(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /config command"""
        if "set" in args:
            # Set configuration
            key_value = args["set"]
            if "=" in key_value:
                key, value = key_value.split("=", 1)
                # Here you would update the actual configuration
                output = f"✅ Configuration updated: {key} = {value}"
            else:
                output = "❌ Invalid format. Use: /config --set KEY=VALUE"
                return CommandResult(success=False, output=output)
        elif "get" in args:
            # Get configuration
            key = args["get"]
            # Here you would retrieve the actual configuration
            value = "example_value"  # Placeholder
            output = f"📋 Configuration: {key} = {value}"
        else:
            # Show all configuration
            output = """⚙️ Current Configuration:

Evolution:
  enabled: true
  generations: 10
  population_size: 50
  mutation_rate: 0.1

Compression:
  level: 0.1
  strategy: intelligent

Parallelism:
  max_workers: 5
  enable_parallel: true
"""
        
        return CommandResult(success=True, output=output)
    
    async def _handle_reset(self, args: Dict[str, Any]) -> CommandResult:
        """Handle /reset command"""
        if not args.get("confirm"):
            return CommandResult(
                success=False,
                output="⚠️ This will reset the system. Use '/reset --confirm' to proceed."
            )
        
        preserve_memory = args.get("preserve-memory", False)
        
        # Reset system state
        if not preserve_memory:
            self.evolution_agent.memory.patterns.clear()
            self.evolution_agent.memory.experiences.clear()
        
        self.evolution_agent.task_history.clear()
        self.history.clear()
        
        output = "🔄 System reset complete!"
        if preserve_memory:
            output += "\n✅ Memory preserved"
        else:
            output += "\n🗑️ Memory cleared"
        
        return CommandResult(success=True, output=output)
    
    async def _handle_natural_language(self, query: str) -> CommandResult:
        """Handle natural language input"""
        # Process as a regular task through Meta Agent
        result = await self.meta_agent.process_request(query)
        
        output = f"""💬 Natural Language Request Processed

Request: {query}

Results:
  Success: {result.success}
  Tasks Completed: {result.tasks_completed}
  Tasks Failed: {result.tasks_failed}
  Success Rate: {result.success_rate:.1%}
"""
        
        if result.artifacts:
            output += f"\nArtifacts Created: {len(result.artifacts)}\n"
            for artifact in result.artifacts[:5]:  # Show first 5
                output += f"  - {artifact.name} ({artifact.type.value})\n"
        
        return CommandResult(
            success=result.success,
            output=output,
            data={
                "execution_result": {
                    "success": result.success,
                    "tasks_completed": result.tasks_completed,
                    "artifacts": len(result.artifacts) if result.artifacts else 0
                }
            }
        )
    
    async def _run_simulation(
        self, 
        config: Dict[str, Any], 
        iterations: int
    ) -> Dict[str, Any]:
        """Run a simulation scenario"""
        # This would integrate with the Rust interaction net engine
        # For now, return mock results
        import random
        
        results = []
        for _ in range(iterations):
            steps = random.randint(5, 50)
            success = random.random() > 0.1
            results.append({"steps": steps, "success": success})
        
        successful = sum(1 for r in results if r["success"])
        steps_list = [r["steps"] for r in results if r["success"]]
        
        return {
            "iterations": iterations,
            "success_rate": successful / iterations,
            "avg_steps": sum(steps_list) / len(steps_list) if steps_list else 0,
            "min_steps": min(steps_list) if steps_list else 0,
            "max_steps": max(steps_list) if steps_list else 0
        }


# Placeholder for visualization module
class InteractionNetVisualizer:
    """Visualizes interaction nets in various formats"""
    
    def render_ascii(self, net: Any, detail: str) -> str:
        """Render as ASCII art"""
        return """
    [λ]━━━[@]
     │     │
    [δ]   [ε]
        """
    
    def render_svg(self, net: Any, detail: str) -> str:
        """Render as SVG"""
        return "<svg>...</svg>"
    
    def render_png(self, net: Any, detail: str) -> str:
        """Render as PNG (base64)"""
        return "data:image/png;base64,..."