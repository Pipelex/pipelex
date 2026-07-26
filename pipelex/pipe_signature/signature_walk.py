"""Dependency-graph walk for `PipeSignature` detection.

These two functions walk a pipe's dependency graph to find every reachable signature.
They live outside `PipeAbstract` on purpose: the walk needs `get_optional_pipe` to
resolve dependency codes to pipes, and `pipe_abstract` importing `pipelex.interpreter_hub` would
form an import cycle (`pipe_abstract → hub → library → pipe_library → pipe_abstract`).
Keeping the walk here — downstream of `hub` — keeps `pipe_abstract` cycle-free.
"""

from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.interpreter_hub import get_optional_pipe


def collect_signature_refs(pipe: PipeAbstract, *, visited: set[str] | None = None) -> set[str]:
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
    *,
    current_path: list[str] | None = None,
    paths: dict[str, list[str]] | None = None,
) -> dict[str, list[str]]:
    """Return mapping from signature pipe_ref to the longest dep chain that reaches it.

    Each value is the ordered list of controller pipe_refs traversed (entry-point first).
    Keys and path entries are qualified pipe_refs. Companion of `collect_signature_refs`
    used to render the dep chain that reaches each unimplemented signature. When a signature
    is reachable by several paths (a diamond), the longest — most informative — chain is kept.
    """
    if current_path is None:
        current_path = []
    if paths is None:
        paths = {}
    # Cycle break: a pipe already on the active dependency path is a back edge — stop.
    # Unlike a global visited set, this still explores diamonds (distinct paths that
    # re-converge on the same signature), so we can keep the longest, most informative chain.
    if pipe.pipe_ref in current_path:
        return paths
    if pipe.is_signature:
        existing = paths.get(pipe.pipe_ref)
        if existing is None or len(current_path) > len(existing):
            paths[pipe.pipe_ref] = list(current_path)
    next_path = [*current_path, pipe.pipe_ref]
    # Sort dep iteration for stable dep-chain output (see `collect_signature_refs`).
    for dep_code in sorted(pipe.pipe_dependencies()):
        dep_pipe = get_optional_pipe(pipe_code=dep_code)
        if dep_pipe is None:
            continue
        collect_signature_paths(pipe=dep_pipe, current_path=next_path, paths=paths)
    return paths
