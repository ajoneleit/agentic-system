"""Interaction Net Visualizer for /zero.

Provides visualization capabilities for interaction nets, showing
graph structure, reduction steps, and evolution progress.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from structlog import get_logger

logger = get_logger(__name__)


@dataclass
class NetNode:
    """Represents a node in the interaction net."""

    id: str
    node_type: str
    label: str
    position: tuple[float, float]
    properties: dict[str, Any]


@dataclass
class NetEdge:
    """Represents an edge in the interaction net."""

    source: str
    target: str
    edge_type: str
    label: str
    properties: dict[str, Any]


@dataclass
class NetGraph:
    """Represents the complete interaction net graph."""

    nodes: list[NetNode]
    edges: list[NetEdge]
    metadata: dict[str, Any]


class InteractionNetVisualizer:
    """Visualizes interaction nets for the /zero system."""

    def __init__(self):
        """Initialize the visualizer."""
        self.current_graph: Optional[NetGraph] = None

    def create_graph_from_state(self, state: dict[str, Any]) -> NetGraph:
        """Create a graph representation from system state.

        Args:
            state: System state dictionary

        Returns:
            NetGraph object representing the interaction net

        """
        nodes = []
        edges = []

        # Create nodes from state
        if "agents" in state:
            for i, agent in enumerate(state["agents"]):
                node = NetNode(
                    id=f"agent_{i}",
                    node_type="agent",
                    label=agent.get("name", f"Agent {i}"),
                    position=(i * 100, 50),
                    properties=agent,
                )
                nodes.append(node)

        if "tasks" in state:
            for i, task in enumerate(state["tasks"]):
                node = NetNode(
                    id=f"task_{i}",
                    node_type="task",
                    label=task.get("name", f"Task {i}"),
                    position=(i * 100, 150),
                    properties=task,
                )
                nodes.append(node)

        # Create edges from dependencies
        if "dependencies" in state:
            for dep in state["dependencies"]:
                edge = NetEdge(
                    source=dep["source"],
                    target=dep["target"],
                    edge_type="dependency",
                    label="depends on",
                    properties=dep,
                )
                edges.append(edge)

        metadata = {
            "created_at": state.get("timestamp", "unknown"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "graph_type": "interaction_net",
        }

        graph = NetGraph(nodes=nodes, edges=edges, metadata=metadata)
        self.current_graph = graph
        return graph

    def generate_svg(self, graph: Optional[NetGraph] = None) -> str:
        """Generate SVG representation of the interaction net.

        Args:
            graph: Graph to visualize (uses current if None)

        Returns:
            SVG string

        """
        if graph is None:
            graph = self.current_graph

        if graph is None:
            return "<svg><text>No graph available</text></svg>"

        svg_parts = [
            '<svg width="800" height="600" xmlns="http://www.w3.org/2000/svg">',
            "<defs>",
            '<marker id="arrowhead" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">',
            '<polygon points="0 0, 10 3.5, 0 7" fill="black"/>',
            "</marker>",
            "</defs>",
        ]

        # Draw edges first (so they appear behind nodes)
        for edge in graph.edges:
            source_node = next((n for n in graph.nodes if n.id == edge.source), None)
            target_node = next((n for n in graph.nodes if n.id == edge.target), None)

            if source_node and target_node:
                svg_parts.append(
                    f'<line x1="{source_node.position[0]}" y1="{source_node.position[1]}" '
                    f'x2="{target_node.position[0]}" y2="{target_node.position[1]}" '
                    f'stroke="black" stroke-width="2" marker-end="url(#arrowhead)"/>'
                )

        # Draw nodes
        for node in graph.nodes:
            x, y = node.position
            color = "lightblue" if node.node_type == "agent" else "lightgreen"

            svg_parts.extend(
                [
                    f'<circle cx="{x}" cy="{y}" r="30" fill="{color}" stroke="black" stroke-width="2"/>',
                    f'<text x="{x}" y="{y}" text-anchor="middle" font-size="12">{node.label}</text>',
                ]
            )

        # Add metadata
        svg_parts.append(
            f'<text x="10" y="20" font-size="14">Nodes: {graph.metadata["node_count"]}, '
            f'Edges: {graph.metadata["edge_count"]}</text>'
        )

        svg_parts.append("</svg>")
        return "".join(svg_parts)

    def generate_ascii(self, graph: Optional[NetGraph] = None) -> str:
        """Generate ASCII representation of the interaction net.

        Args:
            graph: Graph to visualize (uses current if None)

        Returns:
            ASCII string representation

        """
        if graph is None:
            graph = self.current_graph

        if graph is None:
            return "No graph available"

        ascii_parts = []
        ascii_parts.append("Interaction Net Visualization")
        ascii_parts.append("=" * 30)

        # Show nodes
        ascii_parts.append("\nNodes:")
        for node in graph.nodes:
            ascii_parts.append(f"  [{node.node_type}] {node.label} (id: {node.id})")

        # Show edges
        ascii_parts.append("\nConnections:")
        for edge in graph.edges:
            ascii_parts.append(f"  {edge.source} -> {edge.target} ({edge.label})")

        # Show metadata
        ascii_parts.append("\nGraph Stats:")
        ascii_parts.append(f"  Nodes: {graph.metadata['node_count']}")
        ascii_parts.append(f"  Edges: {graph.metadata['edge_count']}")

        return "\n".join(ascii_parts)

    def export_graph(self, filepath: Path, format: str = "json") -> bool:
        """Export the current graph to file.

        Args:
            filepath: Path to save the graph
            format: Export format ('json', 'svg', 'ascii')

        Returns:
            True if successful

        """
        if self.current_graph is None:
            logger.error("No graph available to export")
            return False

        try:
            if format == "json":
                graph_data = {
                    "nodes": [
                        {
                            "id": node.id,
                            "type": node.node_type,
                            "label": node.label,
                            "position": node.position,
                            "properties": node.properties,
                        }
                        for node in self.current_graph.nodes
                    ],
                    "edges": [
                        {
                            "source": edge.source,
                            "target": edge.target,
                            "type": edge.edge_type,
                            "label": edge.label,
                            "properties": edge.properties,
                        }
                        for edge in self.current_graph.edges
                    ],
                    "metadata": self.current_graph.metadata,
                }
                with open(filepath, "w") as f:
                    json.dump(graph_data, f, indent=2)

            elif format == "svg":
                svg_content = self.generate_svg()
                with open(filepath, "w") as f:
                    f.write(svg_content)

            elif format == "ascii":
                ascii_content = self.generate_ascii()
                with open(filepath, "w") as f:
                    f.write(ascii_content)

            else:
                logger.error(f"Unsupported export format: {format}")
                return False

            logger.info(f"Graph exported to {filepath} in {format} format")
            return True

        except Exception as e:
            logger.error(f"Failed to export graph: {e}")
            return False

    def create_evolution_visualization(self, generations: list[dict[str, Any]]) -> str:
        """Create a visualization showing evolutionary progress.

        Args:
            generations: List of generation states

        Returns:
            ASCII visualization of evolution

        """
        if not generations:
            return "No evolution data available"

        viz_parts = []
        viz_parts.append("Evolution Progress Visualization")
        viz_parts.append("=" * 40)

        for i, gen in enumerate(generations):
            fitness = gen.get("fitness", 0.0)
            bar_length = int(fitness * 50)  # Scale to 50 chars
            bar = "█" * bar_length + "░" * (50 - bar_length)

            viz_parts.append(f"Gen {i:2d}: [{bar}] {fitness:.3f}")

        # Show improvement
        if len(generations) > 1:
            initial_fitness = generations[0].get("fitness", 0.0)
            final_fitness = generations[-1].get("fitness", 0.0)
            improvement = final_fitness - initial_fitness
            viz_parts.append(f"\nImprovement: {improvement:+.3f}")

        return "\n".join(viz_parts)

    def get_graph_stats(self) -> dict[str, Any]:
        """Get statistics about the current graph.

        Returns:
            Dictionary with graph statistics

        """
        if self.current_graph is None:
            return {"error": "No graph available"}

        node_types = {}
        edge_types = {}

        for node in self.current_graph.nodes:
            node_types[node.node_type] = node_types.get(node.node_type, 0) + 1

        for edge in self.current_graph.edges:
            edge_types[edge.edge_type] = edge_types.get(edge.edge_type, 0) + 1

        return {
            "total_nodes": len(self.current_graph.nodes),
            "total_edges": len(self.current_graph.edges),
            "node_types": node_types,
            "edge_types": edge_types,
            "metadata": self.current_graph.metadata,
        }
