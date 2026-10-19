"""The pipes a refusal of a pipe selection or reference offers in place of the one that names nothing.

A refusal that names a pipe the method does not declare, or that names no pipe where the method gives none to
start from, carries the pipes the caller most likely meant (``request.pipe_not_found``'s ``suggestions``,
``method.pipe_unresolved``'s and ``request.pipe_unspecified``'s ``candidates``). Each is written as the qualified
``domain.pipe_code`` a selection accepts, whatever form the name that missed was written in.
"""

from collections.abc import Iterable
from typing import TYPE_CHECKING

from pipelex.core.qualified_ref import QualifiedRef
from pipelex.tools.misc.string_utils import close_matches

if TYPE_CHECKING:
    from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint

# The declaration a `method.pipe_unresolved` refusal names as its `pipe` when the reference that names nothing is a
# `main_pipe`, of a bundle or of a package manifest: no pipe declares that reference, so the refusal names the
# declaration that holds it.
MAIN_PIPE_DECLARATION = "main_pipe"

# How near a pipe code must be to the code that missed to be offered, as difflib's similarity ratio, and how many are offered.
_CLOSE_PIPE_CUTOFF = 0.6
_CLOSE_PIPE_MAX_MATCHES = 5


def declared_pipe_refs(*, blueprints: Iterable["PipelexBundleBlueprint"]) -> list[str]:
    """The qualified refs of every pipe the bundles declare, sorted: the pipes a request sending them may select."""
    return sorted({f"{blueprint.domain}.{pipe_code}" for blueprint in blueprints for pipe_code in blueprint.pipe or {}})


def close_pipe_refs(*, name: str, pipe_refs: Iterable[str]) -> list[str]:
    """The pipe refs whose code is nearest the code ``name`` writes, nearest first; an empty list when none is near.

    ``name`` is matched by its code, the part after its domain and after a dependency alias, so a selection that
    names the right pipe in the wrong domain is offered the pipe it meant. A code declared in several domains offers
    each of its refs.

    Args:
        name: The pipe code or ref that names no pipe, as it was written.
        pipe_refs: The qualified refs of the pipes that may be offered.

    Returns:
        The refs offered, nearest first.
    """
    refs_by_code: dict[str, list[str]] = {}
    for pipe_ref in sorted(set(pipe_refs)):
        refs_by_code.setdefault(_pipe_code_of(ref=pipe_ref), []).append(pipe_ref)
    matches = close_matches(name=_pipe_code_of(ref=name), candidates=refs_by_code, cutoff=_CLOSE_PIPE_CUTOFF, max_matches=_CLOSE_PIPE_MAX_MATCHES)
    return [pipe_ref for code in matches for pipe_ref in refs_by_code[code]]


def _pipe_code_of(*, ref: str) -> str:
    """The pipe code a ref writes, without its dependency alias or its domain."""
    if QualifiedRef.has_cross_package_prefix(ref):
        ref = QualifiedRef.split_cross_package_ref(ref).remainder
    return ref.rsplit(".", 1)[-1]
