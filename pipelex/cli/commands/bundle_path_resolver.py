"""Path-to-bundle resolution for human CLI bundle commands.

``pipelex validate bundle`` and ``pipelex fix bundle`` must resolve the user's ``path`` argument identically: fix must
patch exactly what validate judged, a bundle file or a method's whole folder. ``pipelex build inputs bundle`` and
``pipelex build output bundle`` act on the same pipe a run of the same folder starts at. The shared core
(``pipelex.cli.judged_target`` and ``pipelex.cli.bundle_target_resolution``) owns the decision, the one every command
taking a bundle path makes, ``run bundle`` included; this module owns the human text-stream errors.
"""

from pathlib import Path
from typing import NamedTuple, NoReturn

import typer

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.bundle_target_resolution import (
    BundleTargetResolutionError,
    FolderReading,
    resolve_bundle_target_core,
)
from pipelex.cli.error_handlers import handle_pre_boot_config_error
from pipelex.cli.judged_target import JudgedBundleTarget, resolve_judged_target
from pipelex.libraries.exceptions import EmptyMethodTreeError
from pipelex.pipeline.exceptions import MethodEntryError, ValidateBundleError
from pipelex.pipeline.method_entry import MethodEntry


def _stringify_library_dirs(library_dirs: list[Path] | None) -> list[str] | None:
    if library_dirs is None:
        return None
    return [str(library_dir) for library_dir in library_dirs]


def _echo_method_entry(*, entry: MethodEntry) -> None:
    """Say which pipe of a method's folder a command acts on, when the protocol's rule selected it."""
    typer.echo(f"Using the method's main pipe {entry.pipe_ref}, in {entry.tree_path}")


def _refuse_not_a_bundle_target(*, error: BundleTargetResolutionError, command: str, not_a_bundle_hint: str, exit_code: int) -> NoReturn:
    typer.secho(
        f"Failed to {command}: '{error.input_path}' is not a .mthds file or directory.\n{not_a_bundle_hint}",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(exit_code)


def resolve_bundle_target(
    path: str,
    *,
    library_dir: list[str] | None,
    command: str,
    not_a_bundle_hint: str,
) -> JudgedBundleTarget:
    """Resolve the ``path`` argument of ``validate bundle`` or ``fix bundle`` into what the command judges.

    A folder is read as its method tree and judged whole, every bundle of it, as the MTHDS protocol's validation judges
    a method: it needs no pipe to start at. The folder joins the library directories, ahead of ``library_dir``, so its
    files are in the fix write scope, being user-passed.

    No verdict is produced, exit 2 with a red message on stderr, for a folder holding no bundle, for a path that is
    neither a ``.mthds`` file nor a directory, and for a configuration that does not validate, read for the tree's
    limits before the boot, which ``pipelex-agent validate bundle`` and ``pipelex-agent fix bundle`` refuse with the
    same exit code. The same configuration reached at the boot itself, as a bundle file reaches it, keeps the boot's
    own exit code, 1, which L-260930-8873aa settles. A folder whose tree is refused is the invalid verdict, which each
    command reports as its own: ``validate`` as an invalid bundle, ``fix`` as a fix that fails.

    Both ``path`` and each ``library_dir`` entry have ``~`` expanded before resolution, so home-relative inputs behave
    like every other CLI path argument.

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a method's folder).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.
        command: The human command name (e.g. ``"validate"``, ``"fix"``), used in error messages
            (``Failed to {command}: ...``).
        not_a_bundle_hint: Command-specific usage hint appended when ``path`` is neither a ``.mthds`` file nor a
            directory.

    Raises:
        ValidateBundleError: For a folder, its tree is refused or past this machine's limits: the invalid verdict.
    """
    try:
        result = resolve_judged_target(path=path, library_dir=library_dir)
    except EmptyMethodTreeError as exc:
        typer.secho(f"Failed to {command}: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    except PipelexConfigError as exc:
        handle_pre_boot_config_error(exc=exc, command=command, exit_code=2)

    if isinstance(result, BundleTargetResolutionError):
        _refuse_not_a_bundle_target(error=result, command=command, not_a_bundle_hint=not_a_bundle_hint, exit_code=2)
    return result


class BuildBundleTarget(NamedTuple):
    """What a ``build`` command reads off a bundle path: the bundle, the pipe, the library, and where it writes."""

    #: The file named, or the bundle defining a folder's entry; None for a folder whose pipe was named, which loads as
    #: the method's library, as ``run bundle`` runs it.
    bundle_path: Path | None
    #: The pipe named, else a folder's entry pipe as ``domain.pipe_code``; None for a file named alone.
    pipe_code: str | None
    #: The folder, then the ``-L`` directories; None for a file named with no ``-L``.
    library_dir: list[str] | None
    #: The folder, where a generated file goes by default (``run bundle`` finds its inputs there); None for a file.
    default_output_dir: Path | None


def resolve_build_bundle_target(
    *,
    path: str,
    library_dir: list[str] | None,
    pipe_override: str | None,
    command: str,
    not_a_bundle_hint: str,
) -> BuildBundleTarget:
    """Resolve a ``build ... bundle`` command's ``path`` argument, as ``run bundle`` reads the same arguments.

    A folder is read as its method tree. With no pipe named, the command acts on the pipe the method starts at by the
    MTHDS protocol's rule, in the bundle defining it; with a pipe named, it loads the method as its library. A folder
    with no single pipe to start at, a folder that does not load, a path that is neither a ``.mthds`` file nor a
    directory, and a configuration that does not validate, read for the tree's limits before the boot, exit 1 with a
    red message on stderr naming the command, as every ``build`` failure does.

    Args:
        path: The user's ``path`` argument (a ``.mthds`` file or a method's folder).
        library_dir: The ``-L/--library-dir`` values as passed, or ``None``.
        pipe_override: The ``--pipe`` value, or ``None``.
        command: The human command name (``"build inputs"`` or ``"build output"``), used in error messages
            (``Failed to {command}: ...``).
        not_a_bundle_hint: Command-specific usage hint appended when ``path`` is neither a ``.mthds`` file nor a
            directory.
    """
    try:
        result = resolve_bundle_target_core(path, library_dir=library_dir, reading=FolderReading.ENTRY_PIPE, pipe_override=pipe_override)
    except MethodEntryError as exc:
        typer.secho(f"Failed to {command}: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except ValidateBundleError as exc:
        typer.secho(f"Failed to {command}: the method at '{path}' does not load: {exc.message}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except PipelexConfigError as exc:
        handle_pre_boot_config_error(exc=exc, command=command, exit_code=1)

    if isinstance(result, BundleTargetResolutionError):
        _refuse_not_a_bundle_target(error=result, command=command, not_a_bundle_hint=not_a_bundle_hint, exit_code=1)
    if result.entry is not None:
        _echo_method_entry(entry=result.entry)
    return BuildBundleTarget(
        bundle_path=result.bundle_path,
        pipe_code=result.pipe_code,
        library_dir=_stringify_library_dirs(result.library_dirs),
        default_output_dir=result.method_dir,
    )
