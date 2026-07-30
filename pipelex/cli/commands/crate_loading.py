"""Shared CLI helper: assemble a bundle closure and emit the normalized library crate.

Both `pipelex resolve` and the `pipelex codegen` family need the same thing — load the closure,
require it to be **valid**, and normalize it into the flat, self-contained crate the projections read.
Centralizing it here keeps the resolve/validate verdict contract in one place: a structurally invalid
library is a negative verdict, a closure that could not be assembled is no verdict, and an internal
invariant failure (`CrateNormalizationError`) is deliberately left to surface rather than masked as a
verdict. `load_normalized_crate` is the presentation-free core (typed exceptions); the bare-CLI
wrapper `load_normalized_crate_or_exit` maps them to the 1/2 exit codes, and the agent CLI maps the
same exceptions to its structured error envelope.

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
