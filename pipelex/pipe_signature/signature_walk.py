"""Dependency-graph walk for `PipeSignature` detection.

These two functions walk a pipe's dependency graph to find every reachable signature.
They live outside `PipeAbstract` on purpose: the walk needs `get_optional_pipe` to
resolve dependency codes to pipes, and `pipe_abstract` importing `pipelex.hub` would
form an import cycle (`pipe_abstract → hub → library → pipe_library → pipe_abstract`).
Keeping the walk here — downstream of `hub` — keeps `pipe_abstract` cycle-free.
"""

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.hub import get_optional_pipe


def collect_signature_refs(pipe: PipeAbstract, visited: set[str] | None = None) -> set[str]:
    """Return the qualified pipe_refs of every signature reachable from `pipe`.

    Walks `pipe.pipe_dependencies()`, resolving each dependency via `get_optional_pipe`.
    Unresolved dependencies are skipped silently. Cycles are broken via the `visited`
    set keyed by qualified pipe_ref.
    """
    if visited is None:
        visited = set()
    if pipe.pipe_ref in visited:
        return set()
    visited.add(pipe.pipe_ref)

    found: set[str] = set()
    if pipe.is_signature:
        found.add(pipe.pipe_ref)
    # Sort dep iteration so traversal order — and thus the dep chain recorded in
    # `collect_signature_paths` — is stable across runs.
    for dep_code in sorted(pipe.pipe_dependencies()):
        dep_pipe = get_optional_pipe(pipe_code=dep_code)
        if dep_pipe is None:
            continue
        found.update(collect_signature_refs(pipe=dep_pipe, visited=visited))
    return found


def collect_signature_paths(
    pipe: PipeAbstract,
    visited: set[str] | None = None,
    current_path: list[str] | None = None,
) -> dict[str, list[str]]:
    """Return mapping from signature pipe_ref to the dep chain that reached it.

    Each value is the ordered list of controller pipe_refs traversed (entry-point first).
    Keys and path entries are qualified pipe_refs. Companion of `collect_signature_refs`
    used to render the dep chain in `SignaturesNotAllowedError`.
    """
    if visited is None:
        visited = set()
    if current_path is None:
        current_path = []
    if pipe.pipe_ref in visited:
        return {}
    visited.add(pipe.pipe_ref)

    paths: dict[str, list[str]] = {}
    next_path = [*current_path, pipe.pipe_ref]
    if pipe.is_signature:
        paths[pipe.pipe_ref] = list(current_path)
    # Sort dep iteration for stable dep-chain output (see `collect_signature_refs`).
    for dep_code in sorted(pipe.pipe_dependencies()):
        dep_pipe = get_optional_pipe(pipe_code=dep_code)
        if dep_pipe is None:
            continue
        sub_paths = collect_signature_paths(pipe=dep_pipe, visited=visited, current_path=next_path)
        for sig_ref, sub_path in sub_paths.items():
            if sig_ref not in paths:
                paths[sig_ref] = sub_path
    return paths
