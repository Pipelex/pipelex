"""Path-to-bundle resolution for agent CLI bundle commands.

``validate bundle`` and ``fix bundle`` must resolve the user's ``path`` argument identically: fix must patch exactly
what validate judged, a bundle file or a method's whole folder. The shared core (``pipelex.cli.bundle_target_resolution``)
owns the decision, the one every command taking a bundle path makes, ``run bundle`` included; this wrapper owns the
agent error envelopes of a target that names nothing to judge.
"""

from pathlib import Path
from typing import NamedTuple

from mthds.method_tree.models import MethodTree

from pipelex.cli.agent_cli.commands.agent_output import agent_error
from pipelex.cli.bundle_target_resolution import (
    BundleTargetResolutionError,
    FolderReading,
    resolve_bundle_target_core,
)
from pipelex.libraries.exceptions import EmptyMethodTreeError


class AgentBundleTarget(NamedTuple):
    """What an agent ``validate`` or ``fix`` judges: one bundle file, or a method's whole folder, and its library."""

    #: The file named, or None for a folder.
    bundle_path: Path | None
    #: The folder named, judged as its whole method tree, or None for a file.
    method_dir: Path | None
    #: The folder's method tree, or None for a file.
    method_tree: MethodTree | None
    #: The folder, then the ``-L`` directories, ``~`` expanded; None for a file named with no ``-L``.
    library_dirs: list[Path] | None


def resolve_bundle_target(path: str, *, library_dir: list[str] | None) -> AgentBundleTarget:
    """Resolve the ``path`` argument of ``validate bundle`` or ``fix bundle`` into what the command judges.

    A folder is read as its method tree and judged whole, every bundle of it, as the MTHDS protocol's validation judges
    a method: it needs no pipe to start at. The folder is prepended to the library directories, so its files are in the
    fix write scope, being user-passed.

    A folder holding no bundle and a path that is neither a ``.mthds`` file nor a directory produce no verdict: exit 2
    via ``agent_error``.

    Both ``path`` and each ``library_dir`` entry have ``~`` expanded before resolution, so home-relative inputs behave
    like every other CLI path argument.

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a method's folder).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.

    Raises:
        ValidateBundleError: For a folder, its tree is refused or past this machine's limits: the invalid verdict,
            which the command renders as its own surface does.
    """
    try:
        result = resolve_bundle_target_core(path, library_dir=library_dir, reading=FolderReading.WHOLE_TREE)
    except EmptyMethodTreeError as exc:
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc, exit_code=2)

    if isinstance(result, BundleTargetResolutionError):
        agent_error(
            f"'{result.input_path}' is not a .mthds file or directory. "
            f"Use 'validate pipe <code>' for pipe codes, or 'validate bundle <path>' for .mthds files/directories.",
            error_type="ArgumentError",
            exit_code=2,
        )
    return AgentBundleTarget(
        bundle_path=result.bundle_path,
        method_dir=result.method_dir,
        method_tree=result.method_tree,
        library_dirs=result.library_dirs,
    )
