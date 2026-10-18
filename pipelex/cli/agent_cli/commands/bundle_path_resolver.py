"""Path-to-bundle resolution for agent CLI bundle commands.

``validate bundle`` and ``fix bundle`` must resolve the user's ``path`` argument identically: fix must patch exactly
what validate judged, a bundle file or a method's whole folder. The shared core (``pipelex.cli.judged_target``, over
``pipelex.cli.bundle_target_resolution``) owns the decision, the one every command taking a bundle path makes,
``run bundle`` included; this wrapper owns the agent problems of a target that names nothing to judge, and of a
configuration that cannot be read before the boot.
"""

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_cli_factory import report_agent_init_failure
from pipelex.cli.agent_cli.commands.agent_output import agent_argument_error, agent_error
from pipelex.cli.bundle_target_resolution import BundleTargetResolutionError
from pipelex.cli.judged_target import JudgedBundleTarget, resolve_judged_target
from pipelex.libraries.exceptions import EmptyMethodTreeError


def resolve_bundle_target(path: str, *, library_dir: list[str] | None) -> JudgedBundleTarget:
    """Resolve the ``path`` argument of ``validate bundle`` or ``fix bundle`` into what the command judges.

    A folder is read as its method tree and judged whole, every bundle of it, as the MTHDS protocol's validation judges
    a method: it needs no pipe to start at. The folder is prepended to the library directories; a fix may write any
    bundle of its tree, being user-passed.

    A folder holding no bundle, its problem the error's own, and a path that is neither a ``.mthds`` file nor a
    directory, ``client.argument_invalid``, produce no verdict: exit 2 via ``agent_error``. A configuration that does
    not validate, read for the tree's limits before the boot, is reported as the failed boot it would have been.

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
        result = resolve_judged_target(path=path, library_dir=library_dir)
    except EmptyMethodTreeError as exc:
        agent_error(exc.message, cause=exc, exit_code=2)
    except PipelexConfigError as exc:
        report_agent_init_failure(error=exc)

    if isinstance(result, BundleTargetResolutionError):
        agent_argument_error(
            f"'{result.input_path}' is not a .mthds file or directory. "
            f"Use 'validate pipe <code>' for pipe codes, or 'validate bundle <path>' for .mthds files/directories.",
            argument=str(result.input_path),
            reason="not a .mthds file or a directory",
            exit_code=2,
        )
    return result
