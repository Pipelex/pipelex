"""CLI command `pipelex resolve`: emit the normalized library crate for a bundle closure.

Resolution is a first-class language operation alongside validation: it assembles the library closure,
requires it to be **valid** (a resolution over an invalid library produces a verdict, not a crate), and
emits the normalized crate to stdout in the selected encoding. The success stream is the crate; the
verdict rides the exit code, mirroring the bare `validate` group — `0` resolved, `1` produced a negative
verdict (the library is invalid), `2` no verdict could be produced (nothing to resolve / load failure).

See `docs/specs/pipelex-codegen.md` → "CLI: resolve" and the standard's `library-crate.md`.
"""

from pathlib import Path
from typing import Annotated

import typer
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext
from pipelex.codegen.crate_encoding import CrateEncoding, encode_crate
from pipelex.hub import get_library_manager, get_telemetry_manager
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.execution_seams import load_libraries_and_activate
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "resolve"


def resolve_cmd(
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Directories of .mthds bundles to resolve into the closure (added to --library-dir)."),
    ] = None,
    output_format: Annotated[
        CrateEncoding,
        typer.Option("--format", "-f", help="Crate encoding. Both carry the same fingerprint."),
    ] = CrateEncoding.JSON,
    library_dir: Annotated[
        list[Path] | None,
        typer.Option("--library-dir", "-L", help="Directory of .mthds bundles to load (repeatable)."),
    ] = None,
) -> None:
    """Emit the normalized library crate for a bundle closure to stdout."""
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=False)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)

            combined_dirs: list[Path] = [*(paths or []), *(library_dir or [])]
            library_id = load_libraries_and_activate(combined_dirs or None)

            crate = get_library_manager().get_crate(library_id)
            if crate is None:
                typer.secho("Cannot resolve — no .mthds bundles found in the closure.", fg=typer.colors.RED, err=True)
                raise typer.Exit(2)

            normalized = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
            typer.echo(encode_crate(normalized, encoding=output_format), nl=False)
    except (LibraryLoadingError, PipeLibraryError) as exc:
        # A negative verdict: the library is structurally invalid (failed to load, or a pipe conflict
        # across bundles), so no crate can be produced. Internal invariant errors (e.g.
        # CrateNormalizationError) are deliberately not caught here — they must surface, not be masked.
        typer.secho(f"Cannot resolve — the library is invalid:\n{exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1) from exc
    except FileNotFoundError as exc:
        # No verdict: the closure could not even be assembled.
        typer.secho(f"Cannot resolve — {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    finally:
        Pipelex.teardown_if_needed()
