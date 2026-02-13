"""Query engine for the know-how graph.

Provides type-driven discovery: find pipes by concept compatibility,
check pipe chaining, and search for multi-step pipe chains.
"""

from collections import deque

from pipelex.core.packages.graph.models import (
    ConceptId,
    KnowHowGraph,
    PipeNode,
)


def _concepts_are_compatible(
    output_id: ConceptId,
    input_id: ConceptId,
    graph: KnowHowGraph,
) -> bool:
    """Check if an output concept is compatible with an input concept.

    Compatible means the output is the exact same concept as the input,
    or the output is a refinement (descendant) of the input concept.

    Args:
        output_id: The concept produced by a pipe
        input_id: The concept expected by another pipe's input
        graph: The know-how graph for resolving refinement chains

    Returns:
        True if output_id can satisfy input_id
    """
    visited: set[str] = set()
    current: ConceptId | None = output_id

    while current is not None:
        if current.node_key == input_id.node_key:
            return True
        node_key = current.node_key
        if node_key in visited:
            break  # Cycle detection
        visited.add(node_key)

        concept_node = graph.concept_nodes.get(node_key)
        if concept_node is None:
            break
        current = concept_node.refines

    return False


class KnowHowQueryEngine:
    """Query engine for type-driven discovery on a KnowHowGraph.

    Provides methods to find pipes by concept compatibility, check pipe chaining,
    and search for multi-step pipe chains.
    """

    def __init__(self, graph: KnowHowGraph) -> None:
        self._graph = graph

    def query_what_can_i_do(self, concept_id: ConceptId) -> list[PipeNode]:
        """Find pipes that accept the given concept as input.

        A pipe accepts the concept if any of its input parameters expects
        the exact concept or an ancestor (the concept is-a the expected input
        via the refinement chain).

        Args:
            concept_id: The concept you have available

        Returns:
            List of PipeNodes that can consume this concept
        """
        result: list[PipeNode] = []
        for pipe_node in self._graph.pipe_nodes.values():
            for input_concept_id in pipe_node.input_concept_ids.values():
                if _concepts_are_compatible(concept_id, input_concept_id, self._graph):
                    result.append(pipe_node)
                    break  # Don't add the same pipe twice
        return result

    def query_what_produces(self, concept_id: ConceptId) -> list[PipeNode]:
        """Find pipes that produce the given concept.

        A pipe produces the concept if its output is the exact concept
        or a refinement (descendant) of it.

        Args:
            concept_id: The concept you need

        Returns:
            List of PipeNodes that can produce this concept
        """
        result: list[PipeNode] = []
        for pipe_node in self._graph.pipe_nodes.values():
            if _concepts_are_compatible(pipe_node.output_concept_id, concept_id, self._graph):
                result.append(pipe_node)
        return result

    def check_compatibility(self, source_pipe_key: str, target_pipe_key: str) -> list[str]:
        """Check which target pipe input params are compatible with the source pipe's output.

        Args:
            source_pipe_key: The node_key of the source (producer) pipe
            target_pipe_key: The node_key of the target (consumer) pipe

        Returns:
            List of target pipe input parameter names that are compatible.
            Empty list means the pipes are incompatible.
        """
        source_pipe = self._graph.get_pipe_node(source_pipe_key)
        target_pipe = self._graph.get_pipe_node(target_pipe_key)
        if source_pipe is None or target_pipe is None:
            return []

        compatible_params: list[str] = []
        for param_name, input_concept_id in target_pipe.input_concept_ids.items():
            if _concepts_are_compatible(source_pipe.output_concept_id, input_concept_id, self._graph):
                compatible_params.append(param_name)
        return compatible_params

    def resolve_refinement_chain(self, concept_id: ConceptId) -> list[ConceptId]:
        """Walk up from concept through refines links.

        Args:
            concept_id: The starting concept

        Returns:
            List of [concept, parent, grandparent, ...] following the refinement chain.
            Cycle-safe via visited set.
        """
        chain: list[ConceptId] = []
        visited: set[str] = set()
        current: ConceptId | None = concept_id

        while current is not None:
            node_key = current.node_key
            if node_key in visited:
                break  # Cycle detection
            visited.add(node_key)
            chain.append(current)

            concept_node = self._graph.concept_nodes.get(node_key)
            if concept_node is None:
                break
            current = concept_node.refines

        return chain

    def query_i_have_i_need(
        self,
        input_concept_id: ConceptId,
        output_concept_id: ConceptId,
        max_depth: int = 3,
    ) -> list[list[str]]:
        """Find multi-step pipe chains from input to output concept via BFS.

        Args:
            input_concept_id: The concept you have
            output_concept_id: The concept you need
            max_depth: Maximum number of pipes in a chain

        Returns:
            List of pipe chains (each chain is a list of pipe node_keys),
            sorted shortest-first. Empty if no path found.
        """
        # Find starter pipes: those that accept input_concept_id
        starter_pipes = self.query_what_can_i_do(input_concept_id)
        if not starter_pipes:
            return []

        results: list[list[str]] = []
        # BFS queue: (current_chain, set_of_visited_pipe_keys)
        queue: deque[tuple[list[str], set[str]]] = deque()

        for pipe_node in starter_pipes:
            queue.append(([pipe_node.node_key], {pipe_node.node_key}))

        while queue:
            chain, visited = queue.popleft()
            if len(chain) > max_depth:
                continue

            # Check if last pipe in chain produces the desired output
            last_pipe_key = chain[-1]
            last_pipe = self._graph.get_pipe_node(last_pipe_key)
            if last_pipe is None:
                continue

            if _concepts_are_compatible(last_pipe.output_concept_id, output_concept_id, self._graph):
                results.append(chain)
                continue  # Found a complete chain, don't extend further

            # Don't extend if already at max depth
            if len(chain) >= max_depth:
                continue

            # Find next pipes that can consume this pipe's output
            next_pipes = self.query_what_can_i_do(last_pipe.output_concept_id)
            for next_pipe in next_pipes:
                if next_pipe.node_key not in visited:
                    new_chain = [*chain, next_pipe.node_key]
                    new_visited = visited | {next_pipe.node_key}
                    queue.append((new_chain, new_visited))

        # Sort shortest-first
        results.sort(key=len)
        return results
