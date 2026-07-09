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
from pipelex.codegen.emitters.target import CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.hub import get_telemetry_manager
from pipelex.pipelex import Pipelex
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, save_text_to_path
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
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=False)
    output_root = Path(output_dir)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND}")

            combined_dirs: list[Path] = [*(paths or []), *(library_dir or [])]
            crate = load_normalized_crate_or_exit(library_dirs=combined_dirs or None)

            emitted = emit_types(crate, target=target)
            for emitted_file in emitted:
                destination = output_root / emitted_file.filename
                ensure_directory_for_file_path(file_path=destination)
                save_text_to_path(text=emitted_file.content, path=destination)
                typer.secho(f"Generated {destination}", fg=typer.colors.GREEN)
    finally:
        Pipelex.teardown_if_needed()
