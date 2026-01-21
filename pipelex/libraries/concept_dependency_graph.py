"""Concept dependency graph for topological sorting and cycle detection.

This module provides utilities to analyze concept blueprints for dependencies,
perform topological sorting to determine load order, and detect cycles.
"""

from typing import Any, cast

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import (
    ConceptStructureBlueprint,
    ConceptStructureBlueprintFieldType,
)
from pipelex.libraries.exceptions import LibraryLoadingError


class CycleDetectedError(LibraryLoadingError):
    """Raised when a cycle is detected in concept dependencies."""

    def __init__(self, cycle: list[str]):
        self.cycle = cycle
        cycle_str = " -> ".join(cycle)
        message = f"Cycle detected in concept dependencies: {cycle_str}"
        super().__init__(message)


class ConceptDependencyGraph:
    """Utility for extracting concept dependencies and performing topological sort.

    This class analyzes ConceptBlueprint instances to extract dependencies based on:
    - concept_ref fields (type = "concept")
    - item_concept_ref fields (list of concepts)

    It then performs topological sorting to determine the correct load order,
    ensuring that dependencies are loaded before the concepts that depend on them.
    """

    def __init__(self):
        self._dependencies: dict[str, set[str]] = {}

    def extract_dependencies(self, concept_ref: str, blueprint: ConceptBlueprint) -> set[str]:  # noqa: ARG002
        """Extract concept dependencies from a concept blueprint.

        Extracts dependencies from:
        - concept_ref fields (type = "concept")
        - item_concept_ref fields (list of concepts)
        - refines field (concept inheritance)

        Args:
            concept_ref: The full concept reference (e.g., "myapp.Customer") - kept for API consistency
            blueprint: The concept blueprint to analyze

        Returns:
            A set of concept references that this concept depends on
        """
        dependencies: set[str] = set()

        # Check refines field for concept inheritance dependency
        # Non-native concept refs in refines create a dependency
        if blueprint.refines is not None:
            refines_ref = blueprint.refines
            # Only add non-native concept refs as dependencies
            # Native concepts (e.g., "Text", "native.Text") are always available
            if "." in refines_ref and not refines_ref.startswith("native."):
                dependencies.add(refines_ref)

        # Only blueprints with structure dict can have concept references in fields
        if not isinstance(blueprint.structure, dict):
            return dependencies

        for field_blueprint in blueprint.structure.values():
            # Handle both ConceptStructureBlueprint objects and raw dicts/strings
            if isinstance(field_blueprint, ConceptStructureBlueprint):
                # Check for direct concept reference
                if field_blueprint.type == ConceptStructureBlueprintFieldType.CONCEPT and field_blueprint.concept_ref:
                    dependencies.add(field_blueprint.concept_ref)

                # Check for list of concepts
                if (
                    field_blueprint.type == ConceptStructureBlueprintFieldType.LIST
                    and field_blueprint.item_type == "concept"
                    and field_blueprint.item_concept_ref
                ):
                    dependencies.add(field_blueprint.item_concept_ref)

            elif isinstance(field_blueprint, dict):
                # Handle raw dict representation (cast to typed dict)
                typed_blueprint = cast("dict[str, Any]", field_blueprint)
                field_type: str | None = typed_blueprint.get("type")
                if field_type == "concept":
                    concept_ref_value: str | None = typed_blueprint.get("concept_ref")
                    if concept_ref_value:
                        dependencies.add(concept_ref_value)
                elif field_type == "list":
                    item_type: str | None = typed_blueprint.get("item_type")
                    if item_type == "concept":
                        item_concept_ref: str | None = typed_blueprint.get("item_concept_ref")
                        if item_concept_ref:
                            dependencies.add(item_concept_ref)

        return dependencies

    def topological_sort(self, blueprints: dict[str, ConceptBlueprint]) -> list[str]:
        """Perform topological sort on concept blueprints based on dependencies.

        Args:
            blueprints: A dictionary mapping concept refs to their blueprints

        Returns:
            A list of concept refs in topological order (dependencies first)

        Raises:
            CycleDetectedError: If a cycle is detected in the dependencies
        """
        if not blueprints:
            return []

        # Build the dependency graph
        # graph[A] = {B} means A depends on B
        graph: dict[str, set[str]] = {}
        for concept_ref, blueprint in blueprints.items():
            deps = self.extract_dependencies(concept_ref, blueprint)
            # Filter to only include dependencies that are in our blueprints
            # (external dependencies like native.Text are ignored)
            graph[concept_ref] = {dep for dep in deps if dep in blueprints}

        # Store for cycle detection
        self._dependencies = graph

        # Build reverse graph for Kahn's algorithm
        # reverse_graph[A] = {B} means B depends on A (A is a dependency of B)
        reverse_graph: dict[str, set[str]] = {concept_ref: set() for concept_ref in blueprints}
        for concept_ref, deps in graph.items():
            for dep in deps:
                if dep in reverse_graph:
                    reverse_graph[dep].add(concept_ref)

        # Calculate in-degree (number of dependencies each node has)
        in_degree: dict[str, int] = {concept_ref: len(deps) for concept_ref, deps in graph.items()}

        # Start with nodes that have no dependencies (in_degree == 0)
        # These are the "base" concepts that don't depend on anything
        queue = [concept_ref for concept_ref, degree in in_degree.items() if degree == 0]

        result: list[str] = []

        while queue:
            # Sort to ensure deterministic order
            queue.sort()
            concept_ref = queue.pop(0)
            result.append(concept_ref)

            # For each node that depends on this one, decrement its in-degree
            for dependent in reverse_graph.get(concept_ref, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        # Check if we processed all nodes
        if len(result) != len(blueprints):
            # There's a cycle - find it for a helpful error message
            cycle = self._find_cycle(graph, set(blueprints.keys()) - set(result))
            raise CycleDetectedError(cycle)

        return result

    def _find_cycle(self, graph: dict[str, set[str]], remaining_nodes: set[str]) -> list[str]:
        """Find a cycle in the remaining nodes of the graph.

        Args:
            graph: The dependency graph
            remaining_nodes: Nodes that weren't processed (part of a cycle)

        Returns:
            A list representing the cycle (e.g., ["A", "B", "C", "A"])
        """
        if not remaining_nodes:
            return []

        # Use DFS to find a cycle
        visited: set[str] = set()
        rec_stack: list[str] = []
        rec_set: set[str] = set()

        def dfs(node: str) -> list[str] | None:
            visited.add(node)
            rec_stack.append(node)
            rec_set.add(node)

            for neighbor in graph.get(node, set()):
                if neighbor not in visited:
                    cycle = dfs(neighbor)
                    if cycle:
                        return cycle
                elif neighbor in rec_set:
                    # Found a cycle - extract it
                    cycle_start_idx = rec_stack.index(neighbor)
                    return [*rec_stack[cycle_start_idx:], neighbor]

            rec_stack.pop()
            rec_set.remove(node)
            return None

        for node in remaining_nodes:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle

        # Fallback - shouldn't happen if there's actually a cycle
        remaining_list = list(remaining_nodes)
        return [*remaining_list[:3], next(iter(remaining_nodes))]
