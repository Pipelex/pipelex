"""CLI command `pipelex codegen types`: project the crate's concept set into typed artifacts.

Thin wiring over the `emit_types` engine (`pipelex/codegen/emitters/types_emitter.py`): load and
normalize the closure into a crate, project its concept set for the chosen `--target`, and write each
emitted file under the output root. The verdict (resolved / invalid library) rides the resolve exit
codes via `load_normalized_crate_or_exit`; the success stream is the list of written files.

See `docs/specs/pipelex-codegen.md` -> "CLI: codegen" and "Two axes".
"""

from pathlib import Path
from typing import Annotated

import typer
from posthog import tag

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.crate_loading import load_normalized_crate_or_exit
from pipelex.cli.error_handlers import ErrorContext
from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.pipelex import Pipelex
from pipelex.service_hub import get_telemetry_manager
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "codegen"
SUB_COMMAND = "types"


def codegen_types_cmd(
    target: Annotated[
        CodegenTarget,
        typer.Option("--target", "-t", help="Codegen target flavor (ts-zod, python-pydantic, python-structures)."),
    ],
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Directories of .mthds bundles to resolve into the closure (added to --library-dir)."),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option("--output", "-o", help="Directory the generated files are written into (default: current directory)."),
    ] = ".",
    library_dir: Annotated[
        list[Path] | None,
        typer.Option("--library-dir", "-L", help="Directory of .mthds bundles to load (repeatable)."),
    ] = None,
) -> None:
    """Project the crate's concept set into typed artifacts for the chosen target."""
    # needs_model_specs=True (like `validate`): library validation checks pipe model pins
    # against the deck, so the specs must be loaded even though codegen needs no inference.
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)
    output_root = Path(output_dir).expanduser()

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND}")

            combined_dirs: list[Path] = [*(paths or []), *(library_dir or [])]
            crate = load_normalized_crate_or_exit(library_dirs=combined_dirs or None)

            emitted = emit_types(crate, target=target)
            report = write_stamped_projection(
                emitted,
                output_dir=output_root,
                crate_fingerprint=crate.fingerprint,
                engine_version=get_package_version(),
                kind=CodegenKind.TYPES,
                target=target,
            )
            for filename in report.written:
                typer.secho(f"Generated {output_root / filename}", fg=typer.colors.GREEN)
            for filename in report.unchanged:
                typer.secho(f"Unchanged {output_root / filename}", fg=typer.colors.BLUE)
            for filename in report.removed:
                typer.secho(f"Removed stale {output_root / filename}", fg=typer.colors.YELLOW)
            typer.secho(f"Locked {output_root / report.lock_path}", fg=typer.colors.GREEN)
    finally:
        Pipelex.teardown_if_needed()
