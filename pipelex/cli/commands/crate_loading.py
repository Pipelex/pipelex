"""Shared CLI helper: assemble a bundle closure and emit the normalized library crate.

Both `pipelex resolve` and the `pipelex codegen` family need the same thing — load the closure,
require it to be **valid**, and normalize it into the flat, self-contained crate the projections read.
Centralizing it here keeps the resolve/validate verdict contract in one place: a structurally invalid
library is a negative verdict, a closure that could not be assembled is no verdict, and an internal
invariant failure (`CrateNormalizationError`) is deliberately left to surface rather than masked as a
verdict. `load_normalized_crate` is the presentation-free core (typed exceptions); the bare-CLI
wrapper `load_normalized_crate_or_exit` maps them to the 1/2 exit codes, and the agent CLI maps the
same exceptions to its structured error envelope.

`load_crate_for_concept_projection` is a SECOND, weaker contract for `codegen types` alone — same
crate, but the closure's pipes are never instantiated, so a bundle whose PipeFunc implementation
does not exist yet can still have its structures generated. The two entries are deliberately
separate functions rather than a flag on one: the contract difference is what callers must choose
between, and `resolve` / `codegen inputs` never asked for the weaker one.

See `docs/specs/pipelex-codegen.md` → "CLI: resolve" and the standard's `library-crate.md`.
"""

from pathlib import Path

import typer
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION

from pipelex.interpreter_hub import get_library_manager
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipeline.execution_seams import load_libraries_and_activate


def load_normalized_crate(*, library_dirs: list[Path] | None) -> LibraryCrate:
    """Load, validate, and normalize the crate for a bundle closure.

    Raises:
        LibraryLoadingError: The library is structurally invalid (a negative verdict).
        PipeLibraryError: A pipe conflict across bundles (a negative verdict).
        FileNotFoundError: The closure could not be assembled, or it holds no .mthds bundles (no verdict).
    """
    expanded_library_dirs = [library_dir.expanduser() for library_dir in library_dirs] if library_dirs is not None else None
    library_id = load_libraries_and_activate(expanded_library_dirs)
    crate = get_library_manager().get_crate(library_id)
    if crate is None:
        msg = "no .mthds bundles found in the closure."
        raise FileNotFoundError(msg)
    # CrateNormalizationError (an internal invariant) is deliberately not caught — it must surface.
    return normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)


def load_crate_for_concept_projection(*, library_dirs: list[Path] | None) -> LibraryCrate:
    """Load and normalize the crate for a CONCEPT-ONLY projection — a deliberately weaker contract.

    Same closure assembly, manifest visibility, dependency loading, concept loading and
    domain/concept validation as `load_normalized_crate`, with one difference: the closure's pipe
    blueprints are **not** instantiated into live pipes, so pipe-level validation does not run and
    the customer's `@pipe_func` Python is never imported.

    That is sound only because the projection this feeds reads the concept set alone:
    `resolve_concepts_from_crate` documents that the normalized crate is its single authority (never
    the loader, the class registry, or live pipes), and the crate itself is derived from parsed
    blueprints by `get_crate()` — so the returned crate, fingerprint included, is identical to the
    one `load_normalized_crate` would return for the same closure. It is what closes the PipeFunc
    bootstrap deadlock: writing a `@pipe_func` needs the generated `structures.py`, so generating
    `structures.py` must not need the function already importable.

    A crate from here has NOT been proven runnable. Anything that resolves, runs, or reads a live
    pipe — `resolve`, `codegen inputs`, `run` — must keep calling `load_normalized_crate`.

    Raises:
        LibraryLoadingError: The library is structurally invalid at domain/concept level.
        PipeLibraryError: A pipe conflict across bundles (detected when the crate is assembled).
        FileNotFoundError: The closure could not be assembled, or it holds no .mthds bundles.
    """
    expanded_library_dirs = [library_dir.expanduser() for library_dir in library_dirs] if library_dirs is not None else None
    library_id = load_libraries_and_activate(expanded_library_dirs, is_loading_pipes=False)
    crate = get_library_manager().get_crate(library_id)
    if crate is None:
        msg = "no .mthds bundles found in the closure."
        raise FileNotFoundError(msg)
    return normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)


def load_crate_for_concept_projection_or_exit(*, library_dirs: list[Path] | None) -> LibraryCrate:
    """Load the concept-projection crate, or raise `typer.Exit` per the same policy as resolve.

    Exit codes mirror `load_normalized_crate_or_exit`: `1` structurally invalid, `2` closure not
    assembled. The narrower contract is in what gets checked, not in how failures are reported.
    """
    try:
        return load_crate_for_concept_projection(library_dirs=library_dirs)
    except (LibraryLoadingError, PipeLibraryError) as exc:
        typer.secho(f"Cannot resolve — the library is invalid:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        typer.secho(f"Cannot resolve — {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc


def load_normalized_crate_or_exit(*, library_dirs: list[Path] | None) -> LibraryCrate:
    """Load, validate, and normalize the crate for a bundle closure, or raise `typer.Exit` per policy.

    Exit codes mirror the bare `validate` group: `1` when the library is structurally invalid (a
    negative verdict — failed to load, or a pipe conflict across bundles), `2` when the closure could
    not be assembled at all (no verdict — nothing found / load failure).
    """
    try:
        return load_normalized_crate(library_dirs=library_dirs)
    except (LibraryLoadingError, PipeLibraryError) as exc:
        # Negative verdict: the library is structurally invalid, so no crate can be produced.
        typer.secho(f"Cannot resolve — the library is invalid:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        # No verdict: the closure could not even be assembled.
        typer.secho(f"Cannot resolve — {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
