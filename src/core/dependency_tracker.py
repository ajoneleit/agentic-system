"""Dependency tracking and resolution for artifacts.

This module provides automatic dependency detection, graph management,
and impact analysis for artifact relationships.
"""

import ast
import re
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

import networkx as nx
from structlog import get_logger

from src.core.exceptions import AgenticSystemError
from src.core.interfaces import Artifact, ArtifactType

logger = get_logger(__name__)


class DependencyError(AgenticSystemError):
    """Base exception for dependency-related errors."""
    pass


class CyclicDependencyError(DependencyError):
    """Raised when a dependency cycle is detected."""
    
    def __init__(self, cycle: List[UUID]):
        super().__init__(
            f"Cyclic dependency detected: {' -> '.join(str(id) for id in cycle)}",
            error_code="CYCLIC_DEPENDENCY",
            details={"cycle": [str(id) for id in cycle]}
        )


class DependencyConflictError(DependencyError):
    """Raised when there are conflicting dependency requirements."""
    pass


@dataclass(frozen=True)
class Dependency:
    """Represents a dependency between artifacts."""
    
    source_id: UUID
    target_id: Optional[UUID]
    dependency_type: str  # 'import', 'include', 'extends', etc.
    
    # Language-specific information
    import_path: Optional[str] = None
    version_requirement: Optional[str] = None
    is_dev_dependency: bool = False
    is_optional: bool = False
    
    # Additional metadata - use tuple for hashability
    metadata: Dict[str, Any] = field(default_factory=dict, compare=False, hash=False)


@dataclass
class DependencyGraph:
    """Represents the full dependency graph."""
    
    graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    nodes: Dict[UUID, Dict[str, Any]] = field(default_factory=dict)
    language_analyzers: Dict[str, Any] = field(default_factory=dict)


class DependencyTracker:
    """Tracks and manages dependencies between artifacts."""
    
    def __init__(self):
        """Initialize dependency tracker."""
        self._graph = DependencyGraph()
        self._dependency_cache: Dict[UUID, Set[Dependency]] = {}
        
        # Language-specific analyzers
        self._analyzers = {
            "python": PythonDependencyAnalyzer(),
            "javascript": JavaScriptDependencyAnalyzer(),
            "typescript": TypeScriptDependencyAnalyzer(),
            "java": JavaDependencyAnalyzer(),
            "go": GoDependencyAnalyzer(),
        }
        
        logger.info("DependencyTracker initialized")
    
    async def analyze_artifact(
        self,
        artifact: Artifact,
        known_artifacts: Optional[Dict[str, UUID]] = None
    ) -> Set[Dependency]:
        """Analyze an artifact to detect dependencies.
        
        Args:
            artifact: Artifact to analyze
            known_artifacts: Mapping of artifact names to IDs
            
        Returns:
            Set of detected dependencies
        """
        if artifact.type not in [ArtifactType.SOURCE_CODE, ArtifactType.TEST_CODE]:
            return set()
        
        # Check cache
        if artifact.id in self._dependency_cache:
            return self._dependency_cache[artifact.id]
        
        # Get appropriate analyzer
        language = artifact.language or self._detect_language(artifact)
        analyzer = self._analyzers.get(language)
        
        if not analyzer:
            logger.warning(
                "No analyzer for language",
                language=language,
                artifact_id=str(artifact.id)
            )
            return set()
        
        # Analyze dependencies
        dependencies = set()
        try:
            raw_deps = analyzer.analyze(artifact.content, artifact.path)
            
            # Map to known artifacts
            for dep in raw_deps:
                if known_artifacts and dep.import_path in known_artifacts:
                    # Create new dependency with proper IDs
                    mapped_dep = Dependency(
                        source_id=artifact.id,
                        target_id=known_artifacts[dep.import_path],
                        dependency_type=dep.dependency_type,
                        import_path=dep.import_path,
                        version_requirement=dep.version_requirement,
                        is_dev_dependency=dep.is_dev_dependency,
                        is_optional=dep.is_optional,
                        metadata=dep.metadata
                    )
                    dependencies.add(mapped_dep)
                elif dep.target_id and dep.target_id != UUID(int=0):  # External dependency with ID
                    # Create new dependency with source ID
                    mapped_dep = Dependency(
                        source_id=artifact.id,
                        target_id=dep.target_id,
                        dependency_type=dep.dependency_type,
                        import_path=dep.import_path,
                        version_requirement=dep.version_requirement,
                        is_dev_dependency=dep.is_dev_dependency,
                        is_optional=dep.is_optional,
                        metadata=dep.metadata
                    )
                    dependencies.add(mapped_dep)
                else:
                    # Keep the dependency even without a target ID for analysis purposes
                    mapped_dep = Dependency(
                        source_id=artifact.id,
                        target_id=dep.target_id if dep.target_id != UUID(int=0) else None,
                        dependency_type=dep.dependency_type,
                        import_path=dep.import_path,
                        version_requirement=dep.version_requirement,
                        is_dev_dependency=dep.is_dev_dependency,
                        is_optional=dep.is_optional,
                        metadata=dep.metadata
                    )
                    dependencies.add(mapped_dep)
            
        except Exception as e:
            logger.error(
                "Dependency analysis failed",
                artifact_id=str(artifact.id),
                language=language,
                error=str(e)
            )
        
        # Update cache and graph
        self._dependency_cache[artifact.id] = dependencies
        await self._update_graph(artifact, dependencies)
        
        logger.info(
            "Dependencies analyzed",
            artifact_id=str(artifact.id),
            dependencies_count=len(dependencies)
        )
        
        return dependencies
    
    async def add_dependency(
        self,
        source_id: UUID,
        target_id: UUID,
        dependency_type: str = "import",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dependency:
        """Manually add a dependency between artifacts.
        
        Args:
            source_id: Source artifact ID
            target_id: Target artifact ID
            dependency_type: Type of dependency
            metadata: Additional metadata
            
        Returns:
            Created dependency
        """
        dep = Dependency(
            source_id=source_id,
            target_id=target_id,
            dependency_type=dependency_type,
            metadata=metadata or {}
        )
        
        # Update graph
        # Note: edge direction is reversed for topological sort
        # If A depends on B, we add edge B -> A so B comes before A in build order
        self._graph.graph.add_edge(
            target_id,
            source_id,
            dependency=dep
        )
        
        # Update cache
        if source_id not in self._dependency_cache:
            self._dependency_cache[source_id] = set()
        self._dependency_cache[source_id].add(dep)
        
        # Check for cycles
        if self._has_cycle():
            cycle = self._find_cycle()
            # Remove the edge to maintain acyclic graph
            self._graph.graph.remove_edge(target_id, source_id)
            self._dependency_cache[source_id].discard(dep)
            raise CyclicDependencyError(cycle)
        
        logger.info(
            "Dependency added",
            source=str(source_id),
            target=str(target_id),
            type=dependency_type
        )
        
        return dep
    
    async def get_dependencies(
        self,
        artifact_id: UUID,
        recursive: bool = False,
        include_dev: bool = True
    ) -> Set[UUID]:
        """Get dependencies of an artifact.
        
        Args:
            artifact_id: Artifact to get dependencies for
            recursive: Whether to get transitive dependencies
            include_dev: Whether to include dev dependencies
            
        Returns:
            Set of dependency artifact IDs
        """
        if artifact_id not in self._graph.graph:
            return set()
        
        if recursive:
            # Get all descendants in the graph
            dependencies = set()
            to_visit = deque([artifact_id])
            visited = set()
            
            while to_visit:
                current = to_visit.popleft()
                if current in visited:
                    continue
                
                visited.add(current)
                
                # Get direct dependencies
                # Note: we use predecessors because edges are reversed for build order
                for target in self._graph.graph.predecessors(current):
                    edge_data = self._graph.graph[target][current]
                    dep = edge_data.get('dependency')
                    
                    if dep and (include_dev or not dep.is_dev_dependency):
                        dependencies.add(target)
                        to_visit.append(target)
            
            return dependencies
        else:
            # Get direct dependencies only
            dependencies = set()
            # Note: we use predecessors because edges are reversed for build order
            for target in self._graph.graph.predecessors(artifact_id):
                edge_data = self._graph.graph[target][artifact_id]
                dep = edge_data.get('dependency')
                
                if dep and (include_dev or not dep.is_dev_dependency):
                    dependencies.add(target)
            
            return dependencies
    
    async def get_dependents(
        self,
        artifact_id: UUID,
        recursive: bool = False
    ) -> Set[UUID]:
        """Get artifacts that depend on this artifact.
        
        Args:
            artifact_id: Artifact to get dependents for
            recursive: Whether to get transitive dependents
            
        Returns:
            Set of dependent artifact IDs
        """
        if artifact_id not in self._graph.graph:
            return set()
        
        if recursive:
            # Get all descendants in the graph (using reversed edges)
            return set(nx.descendants(self._graph.graph, artifact_id))
        else:
            # Get direct dependents only (using reversed edges)
            return set(self._graph.graph.successors(artifact_id))
    
    async def get_impact_analysis(
        self,
        artifact_id: UUID,
        change_type: str = "modification"
    ) -> Dict[str, Any]:
        """Analyze the impact of changing an artifact.
        
        Args:
            artifact_id: Artifact being changed
            change_type: Type of change (modification, deletion, etc.)
            
        Returns:
            Impact analysis report
        """
        # Get all dependents
        direct_dependents = await self.get_dependents(artifact_id, recursive=False)
        all_dependents = await self.get_dependents(artifact_id, recursive=True)
        
        # Categorize impact
        impact = {
            "artifact_id": str(artifact_id),
            "change_type": change_type,
            "direct_impact": len(direct_dependents),
            "total_impact": len(all_dependents),
            "directly_affected": [str(id) for id in direct_dependents],
            "all_affected": [str(id) for id in all_dependents],
            "risk_level": self._assess_risk_level(len(all_dependents)),
            "recommendations": []
        }
        
        # Add recommendations based on impact
        if impact["risk_level"] == "high":
            impact["recommendations"].append(
                "Consider creating a new version instead of modifying in-place"
            )
            impact["recommendations"].append(
                "Notify all dependent artifact owners before making changes"
            )
        
        if change_type == "deletion" and direct_dependents:
            impact["recommendations"].append(
                "Cannot safely delete - artifacts depend on this"
            )
            impact["breaking_change"] = True
        
        logger.info(
            "Impact analysis completed",
            artifact_id=str(artifact_id),
            impact_level=impact["risk_level"],
            affected_count=impact["total_impact"]
        )
        
        return impact
    
    async def get_build_order(
        self,
        artifact_ids: Optional[Set[UUID]] = None
    ) -> List[UUID]:
        """Get the order in which artifacts should be built/deployed.
        
        Args:
            artifact_ids: Specific artifacts to order (all if None)
            
        Returns:
            Ordered list of artifact IDs
            
        Raises:
            CyclicDependencyError: If there's a dependency cycle
        """
        # Use subset of graph if specific artifacts requested
        if artifact_ids:
            subgraph = self._graph.graph.subgraph(artifact_ids)
        else:
            subgraph = self._graph.graph
        
        # Check for cycles
        if not nx.is_directed_acyclic_graph(subgraph):
            cycle = self._find_cycle(subgraph)
            raise CyclicDependencyError(cycle)
        
        # Topological sort gives build order
        try:
            build_order = list(nx.topological_sort(subgraph))
            
            logger.info(
                "Build order determined",
                artifacts_count=len(build_order)
            )
            
            return build_order
            
        except nx.NetworkXUnfeasible:
            # This shouldn't happen as we check for cycles above
            raise DependencyError("Cannot determine build order")
    
    async def check_compatibility(
        self,
        artifact_id: UUID,
        new_dependencies: Set[UUID]
    ) -> Tuple[bool, List[str]]:
        """Check if new dependencies are compatible.
        
        Args:
            artifact_id: Artifact to update
            new_dependencies: New dependency set
            
        Returns:
            Tuple of (is_compatible, list of issues)
        """
        issues = []
        
        # Check for cycles
        temp_graph = self._graph.graph.copy()
        for dep_id in new_dependencies:
            temp_graph.add_edge(artifact_id, dep_id)
        
        if not nx.is_directed_acyclic_graph(temp_graph):
            issues.append("Would create dependency cycle")
        
        # Check for version conflicts (simplified for now)
        existing_deps = await self.get_dependencies(artifact_id)
        
        # Check for conflicting dependencies
        # This is where we'd check version requirements, etc.
        
        is_compatible = len(issues) == 0
        
        return is_compatible, issues
    
    async def visualize_dependencies(
        self,
        artifact_id: Optional[UUID] = None,
        max_depth: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate visualization data for dependency graph.
        
        Args:
            artifact_id: Center visualization on this artifact (all if None)
            max_depth: Maximum depth to visualize
            
        Returns:
            Graph data suitable for visualization
        """
        if artifact_id:
            # Get subgraph centered on artifact
            if max_depth:
                # BFS to get nodes within max_depth
                nodes = {artifact_id}
                current_level = {artifact_id}
                
                for _ in range(max_depth):
                    next_level = set()
                    for node in current_level:
                        # Add successors and predecessors
                        next_level.update(self._graph.graph.successors(node))
                        next_level.update(self._graph.graph.predecessors(node))
                    
                    nodes.update(next_level)
                    current_level = next_level
                
                subgraph = self._graph.graph.subgraph(nodes)
            else:
                # Get connected component
                undirected = self._graph.graph.to_undirected()
                component = nx.node_connected_component(undirected, artifact_id)
                subgraph = self._graph.graph.subgraph(component)
        else:
            subgraph = self._graph.graph
        
        # Convert to visualization format
        nodes = []
        edges = []
        
        for node_id in subgraph.nodes():
            node_data = self._graph.nodes.get(node_id, {})
            nodes.append({
                "id": str(node_id),
                "label": node_data.get("name", str(node_id)),
                "type": node_data.get("type", "unknown"),
                "metadata": node_data
            })
        
        for source, target, data in subgraph.edges(data=True):
            dep = data.get('dependency')
            edges.append({
                "source": str(source),
                "target": str(target),
                "type": dep.dependency_type if dep else "unknown",
                "metadata": dep.metadata if dep else {}
            })
        
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "total_nodes": len(nodes),
                "total_edges": len(edges),
                "is_acyclic": nx.is_directed_acyclic_graph(subgraph)
            }
        }
    
    def _detect_language(self, artifact: Artifact) -> Optional[str]:
        """Detect language from artifact."""
        if artifact.language:
            return artifact.language
        
        # Detect from file extension
        if artifact.path:
            ext = artifact.path.suffix.lower()
            language_map = {
                '.py': 'python',
                '.js': 'javascript',
                '.ts': 'typescript',
                '.java': 'java',
                '.go': 'go',
                '.rb': 'ruby',
                '.cpp': 'cpp',
                '.c': 'c',
                '.rs': 'rust',
            }
            return language_map.get(ext)
        
        return None
    
    async def _update_graph(
        self,
        artifact: Artifact,
        dependencies: Set[Dependency]
    ) -> None:
        """Update the dependency graph with new information."""
        # Add/update node
        self._graph.nodes[artifact.id] = {
            "name": artifact.name,
            "type": artifact.type.value,
            "language": artifact.language,
            "path": str(artifact.path) if artifact.path else None
        }
        self._graph.graph.add_node(artifact.id)
        
        # Add edges for dependencies
        # Note: edge direction is reversed for topological sort
        for dep in dependencies:
            if dep.target_id:
                self._graph.graph.add_edge(
                    dep.target_id,
                    artifact.id,
                    dependency=dep
                )
    
    def _has_cycle(self, graph: Optional[nx.DiGraph] = None) -> bool:
        """Check if the graph has cycles."""
        graph = graph or self._graph.graph
        return not nx.is_directed_acyclic_graph(graph)
    
    def _find_cycle(self, graph: Optional[nx.DiGraph] = None) -> List[UUID]:
        """Find a cycle in the graph."""
        graph = graph or self._graph.graph
        try:
            cycle = nx.find_cycle(graph, orientation='original')
            return [edge[0] for edge in cycle]
        except nx.NetworkXNoCycle:
            return []
    
    def _assess_risk_level(self, affected_count: int) -> str:
        """Assess risk level based on impact."""
        if affected_count == 0:
            return "none"
        elif affected_count <= 3:
            return "low"
        elif affected_count <= 10:
            return "medium"
        else:
            return "high"


class LanguageAnalyzer:
    """Base class for language-specific dependency analyzers."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Analyze content for dependencies."""
        raise NotImplementedError


class PythonDependencyAnalyzer(LanguageAnalyzer):
    """Analyzes Python code for dependencies."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Extract Python imports and dependencies."""
        dependencies = set()
        
        try:
            tree = ast.parse(content)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dependencies.add(Dependency(
                            source_id=UUID(int=0),  # Placeholder
                            target_id=UUID(int=0),   # Placeholder
                            dependency_type="import",
                            import_path=alias.name
                        ))
                
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ''
                    for alias in node.names:
                        import_path = f"{module}.{alias.name}" if module else alias.name
                        dependencies.add(Dependency(
                            source_id=UUID(int=0),  # Placeholder
                            target_id=UUID(int=0),   # Placeholder
                            dependency_type="import_from",
                            import_path=import_path
                        ))
        
        except SyntaxError:
            # Fall back to regex parsing
            import_pattern = r'^\s*(?:from\s+(\S+)\s+)?import\s+(.+)$'
            for line in content.splitlines():
                match = re.match(import_pattern, line)
                if match:
                    module, imports = match.groups()
                    if module:
                        dependencies.add(Dependency(
                            source_id=UUID(int=0),
                            target_id=UUID(int=0),
                            dependency_type="import",
                            import_path=module
                        ))
        
        return dependencies


class JavaScriptDependencyAnalyzer(LanguageAnalyzer):
    """Analyzes JavaScript code for dependencies."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Extract JavaScript imports and requires."""
        dependencies = set()
        
        # ES6 imports
        import_pattern = r'import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(import_pattern, content):
            dependencies.add(Dependency(
                source_id=UUID(int=0),
                target_id=UUID(int=0),
                dependency_type="import",
                import_path=match.group(1)
            ))
        
        # CommonJS requires
        require_pattern = r'require\s*\(\s*[\'"]([^\'"]+)[\'"]\s*\)'
        for match in re.finditer(require_pattern, content):
            dependencies.add(Dependency(
                source_id=UUID(int=0),
                target_id=UUID(int=0),
                dependency_type="require",
                import_path=match.group(1)
            ))
        
        return dependencies


class TypeScriptDependencyAnalyzer(JavaScriptDependencyAnalyzer):
    """Analyzes TypeScript code for dependencies."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Extract TypeScript imports."""
        # TypeScript uses same import syntax as ES6 JavaScript
        dependencies = super().analyze(content, path)
        
        # Add TypeScript-specific imports (type imports)
        type_import_pattern = r'import\s+type\s+(?:\{[^}]*\}|\w+)\s+from\s+[\'"]([^\'"]+)[\'"]'
        for match in re.finditer(type_import_pattern, content):
            dependencies.add(Dependency(
                source_id=UUID(int=0),
                target_id=UUID(int=0),
                dependency_type="type_import",
                import_path=match.group(1)
            ))
        
        return dependencies


class JavaDependencyAnalyzer(LanguageAnalyzer):
    """Analyzes Java code for dependencies."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Extract Java imports."""
        dependencies = set()
        
        import_pattern = r'^\s*import\s+(?:static\s+)?([a-zA-Z0-9_.]+);'
        for line in content.splitlines():
            match = re.match(import_pattern, line)
            if match:
                dependencies.add(Dependency(
                    source_id=UUID(int=0),
                    target_id=UUID(int=0),
                    dependency_type="import",
                    import_path=match.group(1)
                ))
        
        return dependencies


class GoDependencyAnalyzer(LanguageAnalyzer):
    """Analyzes Go code for dependencies."""
    
    def analyze(self, content: str, path: Optional[Path] = None) -> Set[Dependency]:
        """Extract Go imports."""
        dependencies = set()
        
        # Single import
        single_import_pattern = r'^\s*import\s+"([^"]+)"'
        for line in content.splitlines():
            match = re.match(single_import_pattern, line)
            if match:
                dependencies.add(Dependency(
                    source_id=UUID(int=0),
                    target_id=UUID(int=0),
                    dependency_type="import",
                    import_path=match.group(1)
                ))
        
        # Multiple imports
        in_import_block = False
        for line in content.splitlines():
            if re.match(r'^\s*import\s*\(', line):
                in_import_block = True
            elif in_import_block and re.match(r'^\s*\)', line):
                in_import_block = False
            elif in_import_block:
                match = re.match(r'^\s*"([^"]+)"', line.strip())
                if match:
                    dependencies.add(Dependency(
                        source_id=UUID(int=0),
                        target_id=UUID(int=0),
                        dependency_type="import",
                        import_path=match.group(1)
                    ))
        
        return dependencies