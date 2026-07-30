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
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.crate_loading import load_normalized_crate_or_exit
from pipelex.cli.error_handlers import ErrorContext
from pipelex.codegen.crate_encoding import CrateEncoding, encode_crate
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_telemetry_manager
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
    # needs_model_specs=True (like `validate`): library validation checks pipe model pins
    # against the deck, so the specs must be loaded even though resolving needs no inference.
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=COMMAND)

            combined_dirs: list[Path] = [*(paths or []), *(library_dir or [])]
            normalized = load_normalized_crate_or_exit(library_dirs=combined_dirs or None)
            typer.echo(encode_crate(normalized, encoding=output_format), nl=False)
    finally:
        Pipelex.teardown_if_needed()
