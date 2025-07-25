"""MECE Decomposer with Context Compression.

Implements Mutually Exclusive, Collectively Exhaustive task decomposition
with intelligent context compression for distributed agent reasoning.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

import networkx as nx
from structlog import get_logger

from src.core.exceptions import TaskDecompositionError
from src.core.interfaces import AgentRole, Task

logger = get_logger(__name__)


@dataclass
class CompressedContext:
    """Represents a compressed context for a task partition."""

    original_size: int
    compressed_size: int
    compression_ratio: float
    essential_info: dict[str, Any]
    context_embedding: Optional[list[float]] = None
    related_contexts: list[str] = field(default_factory=list)

    @property
    def savings(self) -> float:
        """Calculate compression savings percentage."""
        return (1 - self.compression_ratio) * 100


@dataclass
class TaskPartition:
    """Represents a MECE partition of tasks."""

    id: str
    tasks: list[Task]
    context: CompressedContext
    dependencies: set[str]
    parallel_group: int
    estimated_tokens: int

    def is_independent(self) -> bool:
        """Check if partition has no external dependencies."""
        internal_ids = {str(t.id) for t in self.tasks}
        return all(dep in internal_ids for dep in self.dependencies)


class MECEValidator:
    """Validates MECE properties of task decomposition."""

    @staticmethod
    def validate_mutually_exclusive(partitions: list[TaskPartition]) -> bool:
        """Ensure no task appears in multiple partitions."""
        seen_tasks = set()
        for partition in partitions:
            for task in partition.tasks:
                if str(task.id) in seen_tasks:
                    return False
                seen_tasks.add(str(task.id))
        return True

    @staticmethod
    def validate_collectively_exhaustive(
        partitions: list[TaskPartition], original_tasks: list[Task]
    ) -> bool:
        """Ensure all tasks are covered."""
        partition_tasks = set()
        for partition in partitions:
            for task in partition.tasks:
                partition_tasks.add(str(task.id))

        original_ids = {str(t.id) for t in original_tasks}
        return partition_tasks == original_ids

    @staticmethod
    def validate_dependencies(partitions: list[TaskPartition]) -> bool:
        """Ensure dependencies are properly handled."""
        task_to_partition = {}
        for i, partition in enumerate(partitions):
            for task in partition.tasks:
                task_to_partition[str(task.id)] = i

        for partition in partitions:
            for task in partition.tasks:
                for dep_id in task.dependencies:
                    dep_partition = task_to_partition.get(str(dep_id))
                    if dep_partition is not None:
                        # Dependency must be in same or earlier partition
                        if dep_partition > task_to_partition[str(task.id)]:
                            return False
        return True


class ContextCompressor:
    """Intelligent context compression for task partitions."""

    def __init__(self, compression_level: float = 0.1):
        self.compression_level = compression_level
        self.context_cache: dict[str, CompressedContext] = {}

    async def compress_partition(
        self, partition: TaskPartition, global_context: dict[str, Any]
    ) -> CompressedContext:
        """Compress context for a task partition."""
        # Extract relevant context for this partition
        relevant_context = await self._extract_relevant_context(partition.tasks, global_context)

        # Calculate original size
        original_size = len(json.dumps(relevant_context))

        # Compress using intelligent summarization
        compressed = await self._intelligent_compression(relevant_context, partition.tasks)

        compressed_size = len(json.dumps(compressed))
        compression_ratio = compressed_size / original_size if original_size > 0 else 1.0

        context = CompressedContext(
            original_size=original_size,
            compressed_size=compressed_size,
            compression_ratio=compression_ratio,
            essential_info=compressed,
        )

        # Cache for future reference
        self.context_cache[partition.id] = context

        return context

    async def _extract_relevant_context(
        self, tasks: list[Task], global_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Extract only context relevant to given tasks."""
        relevant = {}

        # Extract task-specific requirements
        for task in tasks:
            task_key = f"task_{task.id}"
            relevant[task_key] = {
                "description": task.description,
                "requirements": task.metadata.get("requirements", {}),
                "dependencies": [str(d) for d in task.dependencies],
            }

        # Extract shared context elements
        if "project_info" in global_context:
            relevant["project_info"] = global_context["project_info"]

        if "artifacts" in global_context:
            # Only include artifacts referenced by these tasks
            referenced_artifacts = set()
            for task in tasks:
                referenced_artifacts.update(task.metadata.get("required_artifacts", []))

            relevant["artifacts"] = {
                k: v for k, v in global_context["artifacts"].items() if k in referenced_artifacts
            }

        return relevant

    async def _intelligent_compression(
        self, context: dict[str, Any], tasks: list[Task]
    ) -> dict[str, Any]:
        """Apply intelligent compression to context."""
        compressed = {}

        # Prioritize information by relevance
        priority_info = self._prioritize_information(context, tasks)

        # Keep only top priority information up to compression level
        target_size = int(len(json.dumps(context)) * self.compression_level)
        current_size = 0

        for info in priority_info:
            info_size = len(json.dumps(info["data"]))
            if current_size + info_size <= target_size:
                compressed[info["key"]] = info["data"]
                current_size += info_size
            else:
                # Add summary instead of full data
                compressed[info["key"]] = self._summarize(info["data"])
                break

        return compressed

    def _prioritize_information(
        self, context: dict[str, Any], tasks: list[Task]
    ) -> list[dict[str, Any]]:
        """Prioritize context information by relevance."""
        priorities = []

        for key, value in context.items():
            relevance_score = 0

            # Task-specific info has highest priority
            if key.startswith("task_"):
                relevance_score = 1.0
            # Project info is medium priority
            elif key == "project_info":
                relevance_score = 0.7
            # Artifacts referenced by tasks
            elif key == "artifacts":
                relevance_score = 0.5
            else:
                relevance_score = 0.3

            priorities.append({"key": key, "data": value, "score": relevance_score})

        # Sort by relevance score
        priorities.sort(key=lambda x: x["score"], reverse=True)
        return priorities

    def _summarize(self, data: Any) -> dict[str, Any]:
        """Create a summary of data when full inclusion isn't possible."""
        if isinstance(data, dict):
            return {"_summary": True, "keys": list(data.keys()), "size": len(data)}
        elif isinstance(data, list):
            return {
                "_summary": True,
                "length": len(data),
                "sample": data[:3] if len(data) > 3 else data,
            }
        else:
            return {"_summary": True, "type": type(data).__name__, "value": str(data)[:100]}


class MECEDecomposer:
    """Main MECE decomposition system."""

    def __init__(
        self,
        max_partition_size: int = 5,
        compression_level: float = 0.1,
        enable_parallel: bool = True,
    ):
        self.max_partition_size = max_partition_size
        self.compressor = ContextCompressor(compression_level)
        self.enable_parallel = enable_parallel
        self.validator = MECEValidator()

    async def decompose(
        self, tasks: list[Task], global_context: Optional[dict[str, Any]] = None
    ) -> list[TaskPartition]:
        """Decompose tasks into MECE partitions with compressed contexts."""
        if not tasks:
            return []

        global_context = global_context or {}

        # Build dependency graph
        dep_graph = self._build_dependency_graph(tasks)

        # Find strongly connected components (must be in same partition)
        sccs = list(nx.strongly_connected_components(dep_graph))

        # Create initial partitions from SCCs
        initial_partitions = self._create_initial_partitions(tasks, sccs)

        # Optimize partitions for size and parallelism
        optimized = await self._optimize_partitions(initial_partitions, dep_graph)

        # Compress context for each partition
        final_partitions = []
        for _i, partition_tasks in enumerate(optimized):
            partition = TaskPartition(
                id=str(uuid4()),
                tasks=partition_tasks,
                context=CompressedContext(0, 0, 1.0, {}),  # Placeholder
                dependencies=self._get_partition_dependencies(partition_tasks),
                parallel_group=self._assign_parallel_group(partition_tasks, dep_graph),
                estimated_tokens=self._estimate_tokens(partition_tasks),
            )

            # Compress context
            partition.context = await self.compressor.compress_partition(partition, global_context)

            final_partitions.append(partition)

        # Validate MECE properties
        if not self._validate_partitions(final_partitions, tasks):
            raise TaskDecompositionError("Failed to create valid MECE partitions")

        logger.info(
            "Created MECE partitions",
            partition_count=len(final_partitions),
            total_tasks=len(tasks),
            avg_compression=np.mean([p.context.compression_ratio for p in final_partitions]),
        )

        return final_partitions

    def _build_dependency_graph(self, tasks: list[Task]) -> nx.DiGraph:
        """Build directed graph of task dependencies."""
        graph = nx.DiGraph()

        # Add nodes
        for task in tasks:
            graph.add_node(str(task.id), task=task)

        # Add edges (dependencies)
        for task in tasks:
            for dep_id in task.dependencies:
                if graph.has_node(str(dep_id)):
                    graph.add_edge(str(dep_id), str(task.id))

        return graph

    def _create_initial_partitions(
        self, tasks: list[Task], sccs: list[set[str]]
    ) -> list[list[Task]]:
        """Create initial partitions from strongly connected components."""
        task_map = {str(t.id): t for t in tasks}
        partitions = []
        assigned = set()

        # First, handle SCCs
        for scc in sccs:
            if len(scc) > 1:  # Non-trivial SCC
                partition = [task_map[tid] for tid in scc if tid in task_map]
                partitions.append(partition)
                assigned.update(scc)

        # Handle remaining tasks
        remaining = [t for t in tasks if str(t.id) not in assigned]

        # Group by similar characteristics
        groups = self._group_similar_tasks(remaining)
        partitions.extend(groups)

        return partitions

    def _group_similar_tasks(self, tasks: list[Task]) -> list[list[Task]]:
        """Group tasks by similar characteristics."""
        groups = []

        # Group by role
        role_groups: dict[AgentRole, list[Task]] = {}
        for task in tasks:
            role = task.required_role or AgentRole.CORE_LOGIC
            if role not in role_groups:
                role_groups[role] = []
            role_groups[role].append(task)

        # Split large groups
        for role, role_tasks in role_groups.items():
            if len(role_tasks) <= self.max_partition_size:
                groups.append(role_tasks)
            else:
                # Split into smaller chunks
                for i in range(0, len(role_tasks), self.max_partition_size):
                    groups.append(role_tasks[i : i + self.max_partition_size])

        return groups

    async def _optimize_partitions(
        self, initial: list[list[Task]], dep_graph: nx.DiGraph
    ) -> list[list[Task]]:
        """Optimize partitions for parallelism and efficiency."""
        optimized = initial.copy()

        if self.enable_parallel:
            # Try to merge small partitions that can run in parallel
            changed = True
            while changed:
                changed = False
                for i in range(len(optimized) - 1):
                    for j in range(i + 1, len(optimized)):
                        if self._can_merge(optimized[i], optimized[j], dep_graph):
                            # Merge partitions
                            optimized[i].extend(optimized[j])
                            optimized.pop(j)
                            changed = True
                            break
                    if changed:
                        break

        return optimized

    def _can_merge(
        self, partition1: list[Task], partition2: list[Task], dep_graph: nx.DiGraph
    ) -> bool:
        """Check if two partitions can be merged."""
        # Don't merge if it would exceed size limit
        if len(partition1) + len(partition2) > self.max_partition_size:
            return False

        # Check for circular dependencies
        ids1 = {str(t.id) for t in partition1}
        ids2 = {str(t.id) for t in partition2}

        # Check if any task in partition1 depends on partition2
        for task in partition1:
            for dep in task.dependencies:
                if str(dep) in ids2:
                    return False

        # Check if any task in partition2 depends on partition1
        for task in partition2:
            for dep in task.dependencies:
                if str(dep) in ids1:
                    return False

        return True

    def _get_partition_dependencies(self, tasks: list[Task]) -> set[str]:
        """Get all external dependencies for a partition."""
        internal_ids = {str(t.id) for t in tasks}
        external_deps = set()

        for task in tasks:
            for dep in task.dependencies:
                if str(dep) not in internal_ids:
                    external_deps.add(str(dep))

        return external_deps

    def _assign_parallel_group(self, tasks: list[Task], dep_graph: nx.DiGraph) -> int:
        """Assign parallel execution group based on dependencies."""
        # Use topological generations
        {str(t.id) for t in tasks}

        # Find the maximum generation of any dependency
        max_gen = 0
        for task in tasks:
            for dep in task.dependencies:
                if str(dep) in dep_graph:
                    # This is simplified - in practice would use actual topological sort
                    max_gen = max(max_gen, 1)

        return max_gen

    def _estimate_tokens(self, tasks: list[Task]) -> int:
        """Estimate token usage for a partition."""
        # Simple estimation based on task descriptions and complexity
        tokens = 0
        for task in tasks:
            tokens += len(task.description.split()) * 2  # Rough token estimate
            tokens += task.estimated_complexity * 100  # Complexity factor

        return tokens

    def _validate_partitions(
        self, partitions: list[TaskPartition], original_tasks: list[Task]
    ) -> bool:
        """Validate MECE properties."""
        return (
            self.validator.validate_mutually_exclusive(partitions)
            and self.validator.validate_collectively_exhaustive(partitions, original_tasks)
            and self.validator.validate_dependencies(partitions)
        )


# Import numpy for statistics
import numpy as np
