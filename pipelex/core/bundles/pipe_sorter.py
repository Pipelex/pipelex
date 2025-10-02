"""Topological sorting utilities for pipe dependencies."""

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion
from pipelex.exceptions import PipeDefinitionError


def sort_pipes_by_dependencies(
    pipes: dict[str, PipeBlueprintUnion],
) -> list[tuple[str, PipeBlueprintUnion]]:
    """Sort pipes by their dependencies using depth-first pre-order traversal.

    This performs a depth-first traversal where controllers appear before their dependencies,
    and dependencies are visited in the order specified by the controller (e.g., step order
    for PipeSequence). This ordering is intuitive for understanding pipeline structure.

    Args:
        pipes: Dictionary mapping pipe_code to PipeBlueprintUnion

    Returns:
        List of (pipe_code, pipe_blueprint) tuples sorted with controllers before dependencies.
        For PipeSequence, dependencies follow step order. For others, alphabetical order.

    Raises:
        PipeDefinitionError: If circular dependencies are detected among pipes

    Example:
        >>> pipes = {
        ...     "pipe_c": pipe_c_blueprint,  # sequence with steps: pipe_a, pipe_b
        ...     "pipe_a": pipe_a_blueprint,  # no dependencies
        ...     "pipe_b": pipe_b_blueprint,  # no dependencies
        ... }
        >>> sorted_pipes = sort_pipes_by_dependencies(pipes)
        >>> [code for code, _ in sorted_pipes]
        ['pipe_c', 'pipe_a', 'pipe_b']
    """
    # Find root pipes (those not depended upon by anyone)
    all_dependencies: set[str] = set()
    for pipe_blueprint in pipes.values():
        all_dependencies.update(pipe_blueprint.pipe_dependencies)

    root_pipes = [code for code in pipes if code not in all_dependencies]

    # Depth-first traversal to order pipes
    visited: set[str] = set()
    visiting: set[str] = set()  # For cycle detection
    sorted_pipes: list[tuple[str, PipeBlueprintUnion]] = []

    def visit(pipe_code: str) -> None:
        if pipe_code in visited:
            return
        if pipe_code in visiting:
            msg = f"Circular dependency detected involving pipe: {pipe_code}"
            raise PipeDefinitionError(message=msg)
        if pipe_code not in pipes:
            # Dependency not in this bundle, skip it
            return

        visiting.add(pipe_code)
        pipe_blueprint = pipes[pipe_code]

        # Add current pipe first (pre-order)
        sorted_pipes.append((pipe_code, pipe_blueprint))

        # Visit dependencies in order
        ordered_deps = pipe_blueprint.ordered_pipe_dependencies
        if ordered_deps:
            # Use ordered dependencies (e.g., PipeSequence steps)
            for dep_code in ordered_deps:
                if dep_code in pipes:
                    visit(dep_code)
        else:
            # Use alphabetical order for determinism
            for dep_code in sorted(pipe_blueprint.pipe_dependencies):
                if dep_code in pipes:
                    visit(dep_code)

        visited.add(pipe_code)
        visiting.remove(pipe_code)

    # Start traversal from root pipes (sorted for determinism)
    for pipe_code in sorted(root_pipes):
        visit(pipe_code)

    # Ensure all pipes are included (handle disconnected components)
    for pipe_code in sorted(pipes.keys()):
        if pipe_code not in visited:
            visit(pipe_code)

    return sorted_pipes
