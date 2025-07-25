"""Evolutionary Agent Framework for /zero.

This module implements self-improving agents that use interaction nets
for computation and geometric evolution for optimization.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

import numpy as np
from structlog import get_logger

from src.agents.sub_agent import SubAgent
from src.core.exceptions import TaskExecutionError
from src.core.interfaces import (
    AgentRole,
    Artifact,
    ArtifactType,
    Task,
    TaskContext,
)
from src.core.result import Result
from src.core.task_result import TaskResult

logger = get_logger(__name__)


@dataclass
class Pattern:
    """Represents a learned pattern from successful executions."""

    id: str
    input_signature: dict[str, Any]
    output_signature: dict[str, Any]
    transformation: dict[str, Any]
    fitness_improvement: float
    success_rate: float
    usage_count: int = 0
    created_at: datetime = field(default_factory=datetime.now)

    def matches(self, task: Task, threshold: float = 0.8) -> float:
        """Calculate similarity between this pattern and a task."""
        # Simplified similarity calculation
        task_features = self._extract_features(task)
        pattern_features = self.input_signature.get("features", {})

        common_features = set(task_features.keys()) & set(pattern_features.keys())
        if not common_features:
            return 0.0

        similarity = sum(
            1.0 if task_features[k] == pattern_features[k] else 0.5 for k in common_features
        ) / len(pattern_features)

        return similarity

    def _extract_features(self, task: Task) -> dict[str, Any]:
        """Extract features from a task for pattern matching."""
        return {
            "type": task.metadata.get("type", "unknown"),
            "complexity": task.estimated_complexity,
            "role": task.required_role.value if task.required_role else "any",
            "has_dependencies": bool(task.dependencies),
        }


@dataclass
class InteractionNetState:
    """Represents the state of an interaction net."""

    agents: list[dict[str, Any]]
    connections: list[tuple[str, str]]
    active_pairs: list[tuple[str, str]]
    fitness: float = 0.0

    def to_json(self) -> str:
        """Serialize to JSON for Rust interop."""
        return json.dumps(
            {
                "agents": self.agents,
                "connections": self.connections,
                "active_pairs": self.active_pairs,
                "fitness": self.fitness,
            }
        )

    @classmethod
    def from_json(cls, data: str) -> "InteractionNetState":
        """Deserialize from JSON."""
        obj = json.loads(data)
        return cls(**obj)


class MemoryBank:
    """Persistent memory for patterns and experiences."""

    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.patterns: dict[str, Pattern] = {}
        self.experiences: list[dict[str, Any]] = []
        self._load_memory()

    def _load_memory(self):
        """Load patterns from persistent storage."""
        patterns_file = self.storage_path / "patterns.json"
        if patterns_file.exists():
            with open(patterns_file) as f:
                data = json.load(f)
                for p in data.get("patterns", []):
                    pattern = Pattern(**p)
                    self.patterns[pattern.id] = pattern

    def save_memory(self):
        """Persist patterns to storage."""
        patterns_file = self.storage_path / "patterns.json"
        patterns_file.parent.mkdir(parents=True, exist_ok=True)

        with open(patterns_file, "w") as f:
            json.dump(
                {
                    "patterns": [
                        {k: v for k, v in p.__dict__.items() if k != "created_at"}
                        for p in self.patterns.values()
                    ]
                },
                f,
                indent=2,
            )

    async def find_similar_patterns(self, task: Task, threshold: float = 0.7) -> list[Pattern]:
        """Find patterns similar to the given task."""
        matches = []
        for pattern in self.patterns.values():
            similarity = pattern.matches(task, threshold)
            if similarity >= threshold:
                matches.append((similarity, pattern))

        # Sort by similarity and success rate
        matches.sort(key=lambda x: (x[0], x[1].success_rate), reverse=True)
        return [m[1] for m in matches[:5]]  # Top 5 matches

    def store_pattern(self, pattern: Pattern):
        """Store a new pattern."""
        self.patterns[pattern.id] = pattern
        self.save_memory()
        logger.info(
            "Stored new pattern",
            pattern_id=pattern.id,
            fitness_improvement=pattern.fitness_improvement,
        )

    def update_pattern_usage(self, pattern_id: str, success: bool):
        """Update pattern usage statistics."""
        if pattern_id in self.patterns:
            pattern = self.patterns[pattern_id]
            pattern.usage_count += 1
            if success:
                pattern.success_rate = (
                    pattern.success_rate * (pattern.usage_count - 1) + 1.0
                ) / pattern.usage_count
            else:
                pattern.success_rate = (
                    pattern.success_rate * (pattern.usage_count - 1)
                ) / pattern.usage_count
            self.save_memory()


class EvolutionEngine:
    """Geometric evolution engine for interaction nets."""

    def __init__(self, rust_engine_path: Optional[Path] = None):
        self.rust_engine_path = rust_engine_path or Path("./zero-engine")
        self.population: list[InteractionNetState] = []
        self.generation = 0
        self.best_fitness = 0.0

    async def evolve(
        self,
        initial_state: InteractionNetState,
        fitness_fn: callable,
        generations: int = 10,
        population_size: int = 50,
        mutation_rate: float = 0.1,
    ) -> InteractionNetState:
        """Evolve an interaction net using geometric transformations."""
        # Initialize population
        self.population = [self._mutate(initial_state) for _ in range(population_size)]
        self.population[0] = initial_state  # Keep original

        for gen in range(generations):
            # Evaluate fitness
            fitnesses = await asyncio.gather(*[fitness_fn(state) for state in self.population])

            # Update fitness scores
            for state, fitness in zip(self.population, fitnesses):
                state.fitness = fitness

            # Sort by fitness
            self.population.sort(key=lambda s: s.fitness, reverse=True)
            self.best_fitness = self.population[0].fitness

            logger.debug(
                "Evolution generation completed", generation=gen, best_fitness=self.best_fitness
            )

            # Selection and reproduction
            new_population = []

            # Elitism - keep top 10%
            elite_count = max(1, population_size // 10)
            new_population.extend(self.population[:elite_count])

            # Crossover and mutation
            while len(new_population) < population_size:
                parent1 = self._tournament_select()
                parent2 = self._tournament_select()
                child = self._crossover(parent1, parent2)

                if np.random.random() < mutation_rate:
                    child = self._mutate(child)

                new_population.append(child)

            self.population = new_population
            self.generation += 1

        return self.population[0]  # Return best

    def _mutate(self, state: InteractionNetState) -> InteractionNetState:
        """Apply geometric mutations to the interaction net."""
        mutated = InteractionNetState(
            agents=state.agents.copy(),
            connections=state.connections.copy(),
            active_pairs=state.active_pairs.copy(),
        )

        mutation_type = np.random.choice(["add_agent", "remove_agent", "rewire"])

        if mutation_type == "add_agent" and len(mutated.agents) < 100:
            # Add a new agent
            new_agent = {
                "id": str(uuid4()),
                "type": np.random.choice(["lambda", "application", "duplicator"]),
                "arity": np.random.randint(2, 5),
            }
            mutated.agents.append(new_agent)

        elif mutation_type == "remove_agent" and len(mutated.agents) > 2:
            # Remove a random agent
            idx = np.random.randint(0, len(mutated.agents))
            removed = mutated.agents.pop(idx)
            # Remove associated connections
            mutated.connections = [
                (a, b) for a, b in mutated.connections if a != removed["id"] and b != removed["id"]
            ]

        elif mutation_type == "rewire" and mutated.connections:
            # Rewire a connection
            idx = np.random.randint(0, len(mutated.connections))
            mutated.connections[idx]
            # Create new random connection
            if len(mutated.agents) >= 2:
                a1, a2 = np.random.choice(mutated.agents, 2, replace=False)
                mutated.connections[idx] = (a1["id"], a2["id"])

        return mutated

    def _crossover(
        self, parent1: InteractionNetState, parent2: InteractionNetState
    ) -> InteractionNetState:
        """Crossover two interaction net states."""
        # Simple crossover - take agents from parent1, connections from parent2
        child_agents = parent1.agents[: len(parent1.agents) // 2]
        child_agents.extend(parent2.agents[len(parent2.agents) // 2 :])

        # Filter connections to only include those between existing agents
        agent_ids = {a["id"] for a in child_agents}
        child_connections = [
            (a, b)
            for a, b in parent1.connections + parent2.connections
            if a in agent_ids and b in agent_ids
        ]

        # Remove duplicates
        child_connections = list(set(child_connections))

        return InteractionNetState(
            agents=child_agents, connections=child_connections, active_pairs=[]
        )

    def _tournament_select(self, tournament_size: int = 3) -> InteractionNetState:
        """Tournament selection."""
        tournament = np.random.choice(self.population, tournament_size, replace=False)
        return max(tournament, key=lambda s: s.fitness)


class EvolutionaryAgent(SubAgent):
    """Self-improving agent with interaction net computation and learning."""

    def __init__(
        self,
        agent_id: UUID,
        role: AgentRole = AgentRole.CORE_LOGIC,
        artifact_storage_path: Optional[Path] = None,
        memory_path: Optional[Path] = None,
        evolution_enabled: bool = True,
    ):
        super().__init__(agent_id, role)

        # Initialize memory
        storage_path = artifact_storage_path or Path("./projects")
        memory_path = memory_path or storage_path / "memory"
        self.memory = MemoryBank(memory_path)

        # Initialize evolution engine
        self.evolution_engine = EvolutionEngine()
        self.evolution_enabled = evolution_enabled

        # Performance tracking
        self.task_history: list[dict[str, Any]] = []

    async def _execute_specific_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Execute the evolutionary agent's specific task implementation.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            Result[List[Artifact]] containing artifacts or error

        """
        start_time = datetime.now()

        try:
            # Convert task to interaction net
            initial_net = await self._task_to_interaction_net(task)

            # Find similar patterns
            similar_patterns = await self.memory.find_similar_patterns(task)

            if similar_patterns and self.evolution_enabled:
                # Apply learned patterns
                initial_net = await self._apply_patterns(initial_net, similar_patterns)
                logger.info(
                    "Applied learned patterns",
                    task_id=task.id,
                    patterns_count=len(similar_patterns),
                )

            # Calculate initial fitness
            initial_fitness = await self._calculate_fitness(initial_net)

            # Evolve if enabled
            if self.evolution_enabled:
                evolved_net = await self.evolution_engine.evolve(
                    initial_net, self._calculate_fitness, generations=5, population_size=20
                )
                execution_net = evolved_net
            else:
                execution_net = initial_net

            # Calculate final fitness
            final_fitness = await self._calculate_fitness(execution_net)

            # Execute the task using the evolved net and get artifacts
            artifacts_result = await self._execute_with_net_for_artifacts(
                task, context, execution_net
            )

            if artifacts_result.is_failure():
                return artifacts_result

            artifacts = artifacts_result.unwrap()

            # Learn from execution if successful
            if artifacts and final_fitness > initial_fitness:
                pattern = Pattern(
                    id=str(uuid4()),
                    input_signature=self._extract_task_signature(task),
                    output_signature=self._extract_artifacts_signature(artifacts),
                    transformation=self._extract_transformation(initial_net, execution_net),
                    fitness_improvement=final_fitness - initial_fitness,
                    success_rate=1.0,
                )
                self.memory.store_pattern(pattern)

            # Update pattern usage
            for pattern in similar_patterns:
                self.memory.update_pattern_usage(pattern.id, len(artifacts) > 0)

            # Track performance
            self.task_history.append(
                {
                    "task_id": str(task.id),
                    "success": len(artifacts) > 0,
                    "initial_fitness": initial_fitness,
                    "final_fitness": final_fitness,
                    "patterns_used": len(similar_patterns),
                    "evolution_generations": self.evolution_engine.generation,
                    "duration": (datetime.now() - start_time).total_seconds(),
                }
            )

            return Result.success(artifacts)

        except Exception as e:
            logger.error("Evolutionary execution failed", task_id=task.id, error=str(e))
            return Result.failure(
                TaskExecutionError(
                    message=f"Evolutionary execution failed: {str(e)}",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"error": str(e)},
                )
            )

    async def _task_to_interaction_net(self, task: Task) -> InteractionNetState:
        """Convert a task to an interaction net representation."""
        # Create a basic net structure for the task
        agents = [
            {"id": f"task_{task.id}", "type": "lambda", "arity": 3},
            {"id": f"context_{task.id}", "type": "application", "arity": 2},
        ]

        connections = [(agents[0]["id"], agents[1]["id"])]

        return InteractionNetState(
            agents=agents, connections=connections, active_pairs=connections.copy()
        )

    async def _calculate_fitness(self, net: InteractionNetState) -> float:
        """Calculate fitness of an interaction net."""
        # Simple fitness based on net properties
        fitness = 0.0

        # Reward active pairs (parallelism)
        fitness += len(net.active_pairs) * 0.1

        # Penalize too many agents (complexity)
        fitness -= max(0, len(net.agents) - 10) * 0.05

        # Reward connectivity
        if net.agents:
            connectivity = len(net.connections) / len(net.agents)
            fitness += connectivity * 0.2

        return max(0.0, fitness)

    async def _apply_patterns(
        self, net: InteractionNetState, patterns: list[Pattern]
    ) -> InteractionNetState:
        """Apply learned patterns to an interaction net."""
        modified_net = InteractionNetState(
            agents=net.agents.copy(),
            connections=net.connections.copy(),
            active_pairs=net.active_pairs.copy(),
        )

        for pattern in patterns:
            # Apply transformation from pattern
            transformation = pattern.transformation

            if "add_agents" in transformation:
                for agent in transformation["add_agents"]:
                    modified_net.agents.append(agent)

            if "add_connections" in transformation:
                for conn in transformation["add_connections"]:
                    modified_net.connections.append(tuple(conn))

        return modified_net

    async def _execute_with_net(
        self, task: Task, context: TaskContext, net: InteractionNetState
    ) -> TaskResult:
        """Execute task using the interaction net."""
        # This is where we'd call the Rust engine for actual reduction
        # For now, we'll use the standard execution
        return await super().execute_task(task, context)

    async def _execute_with_net_for_artifacts(
        self, task: Task, context: TaskContext, net: InteractionNetState
    ) -> Result[list[Artifact]]:
        """Execute task using the interaction net and return artifacts."""
        # This is where we'd call the Rust engine for actual reduction
        # For now, we'll use the standard execution via SubAgent
        try:
            # Call the parent class's _execute_specific_task method
            # Since we don't have it in parent, we'll create a simple fallback
            return await self._fallback_execute_task(task, context)
        except Exception as e:
            logger.error("Failed to execute with net for artifacts", task_id=task.id, error=str(e))
            return Result.failure(
                TaskExecutionError(
                    message=f"Net execution failed: {str(e)}",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"error": str(e)},
                )
            )

    async def _fallback_execute_task(
        self, task: Task, context: TaskContext
    ) -> Result[list[Artifact]]:
        """Fallback task execution that creates basic artifacts."""
        try:
            # Create a simple artifact based on the task
            artifact = Artifact(
                id=uuid4(),
                name=f"{task.name.lower().replace(' ', '_')}_evolved.py",
                type=ArtifactType.SOURCE_CODE,
                content=f"# Evolutionary agent output for task: {task.name}\n# {task.description}",
                path=Path(f"{task.name.lower().replace(' ', '_')}_evolved.py"),
                language="python",
                task_id=task.id,
                agent_id=self.id,
                metadata={
                    "evolved": True,
                    "generation": self.evolution_engine.generation,
                    "best_fitness": self.evolution_engine.best_fitness,
                },
            )

            return Result.success([artifact])

        except Exception as e:
            logger.error("Fallback execution failed", task_id=task.id, error=str(e))
            return Result.failure(
                TaskExecutionError(
                    message=f"Fallback execution failed: {str(e)}",
                    agent_id=self.id,
                    task_id=task.id,
                    details={"error": str(e)},
                )
            )

    def _extract_task_signature(self, task: Task) -> dict[str, Any]:
        """Extract signature from task for pattern matching."""
        return {
            "features": {
                "type": task.metadata.get("type", "unknown"),
                "complexity": task.estimated_complexity,
                "role": task.required_role.value if task.required_role else "any",
                "description_length": len(task.description),
            }
        }

    def _extract_result_signature(self, result: TaskResult) -> dict[str, Any]:
        """Extract signature from result."""
        return {
            "success": result.success,
            "artifacts_count": len(result.artifacts) if result.artifacts else 0,
            "has_output": bool(getattr(result, "output", None)),
        }

    def _extract_artifacts_signature(self, artifacts: list[Artifact]) -> dict[str, Any]:
        """Extract signature from artifacts list."""
        return {
            "artifacts_count": len(artifacts),
            "artifact_types": [artifact.type.value for artifact in artifacts],
            "total_size": sum(len(artifact.content) for artifact in artifacts),
            "languages": list({artifact.language for artifact in artifacts if artifact.language}),
        }

    def _extract_transformation(
        self, initial: InteractionNetState, final: InteractionNetState
    ) -> dict[str, Any]:
        """Extract transformation between two net states."""
        initial_agents = {a["id"] for a in initial.agents}
        {a["id"] for a in final.agents}

        added_agents = [a for a in final.agents if a["id"] not in initial_agents]

        initial_conns = set(initial.connections)
        final_conns = set(final.connections)

        added_conns = list(final_conns - initial_conns)

        return {"add_agents": added_agents, "add_connections": added_conns}

    def get_performance_metrics(self) -> dict[str, Any]:
        """Get performance metrics for the agent."""
        if not self.task_history:
            return {}

        total_tasks = len(self.task_history)
        successful_tasks = sum(1 for t in self.task_history if t["success"])

        avg_fitness_improvement = np.mean(
            [t["final_fitness"] - t["initial_fitness"] for t in self.task_history]
        )

        patterns_effectiveness = (
            np.mean([t["patterns_used"] for t in self.task_history if t["success"]])
            if successful_tasks > 0
            else 0
        )

        return {
            "total_tasks": total_tasks,
            "success_rate": successful_tasks / total_tasks if total_tasks > 0 else 0,
            "avg_fitness_improvement": avg_fitness_improvement,
            "patterns_stored": len(self.memory.patterns),
            "patterns_effectiveness": patterns_effectiveness,
            "evolution_enabled": self.evolution_enabled,
        }
