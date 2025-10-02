"""Topological sorting utilities for pipe dependencies."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.exceptions import PipeDefinitionError


def sort_pipes_by_dependencies(
    pipes: dict[str, PipeBlueprintUnion],
) -> list[tuple[str, PipeBlueprintUnion]]:
    """Sort pipes by their dependencies using topological sort.

    Uses Kahn's algorithm to ensure pipes are ordered so that all dependencies
    come before the pipes that depend on them. This is essential for proper
    pipe initialization and validation.

    Args:
        pipes: Dictionary mapping pipe_code to PipeBlueprintUnion

    Returns:
        List of (pipe_code, pipe_blueprint) tuples sorted by dependencies.
        Pipes with no dependencies come first, followed by pipes that depend
        on them, and so on.

    Raises:
        PipeDefinitionError: If circular dependencies are detected among pipes

    Example:
        >>> pipes = {
        ...     "pipe_c": pipe_c_blueprint,  # depends on pipe_a and pipe_b
        ...     "pipe_a": pipe_a_blueprint,  # no dependencies
        ...     "pipe_b": pipe_b_blueprint,  # depends on pipe_a
        ... }
        >>> sorted_pipes = sort_pipes_by_dependencies(pipes)
        >>> [code for code, _ in sorted_pipes]
        ['pipe_a', 'pipe_b', 'pipe_c']
    """
    # Build dependency graph
    in_degree: dict[str, int] = {}
    adjacency_list: dict[str, set[str]] = {}

    # Initialize all pipes
    for pipe_code in pipes:
        in_degree[pipe_code] = 0
        adjacency_list[pipe_code] = set()

    # Build the graph: if pipe A depends on pipe B, then B -> A (B must come before A)
    for pipe_code, pipe_blueprint in pipes.items():
        dependencies = pipe_blueprint.pipe_dependencies
        for dep_code in dependencies:
            # Only track dependencies on pipes that exist in this bundle
            if dep_code in pipes:
                adjacency_list[dep_code].add(pipe_code)
                in_degree[pipe_code] += 1

    # Kahn's algorithm for topological sort
    queue: list[str] = [pipe_code for pipe_code, degree in in_degree.items() if degree == 0]
    sorted_pipes: list[tuple[str, PipeBlueprintUnion]] = []

    while queue:
        # Sort queue to ensure deterministic ordering for pipes at the same level
        queue.sort()
        current = queue.pop(0)
        sorted_pipes.append((current, pipes[current]))

        # Process all pipes that depend on the current pipe
        for dependent in sorted(adjacency_list[current]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Check for circular dependencies
    if len(sorted_pipes) != len(pipes):
        remaining_pipes = set(pipes.keys()) - {code for code, _ in sorted_pipes}
        msg = f"Circular dependency detected among pipes: {remaining_pipes}"
        raise PipeDefinitionError(message=msg)

    return sorted_pipes
