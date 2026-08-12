"""CLI command `pipelex codegen inputs`: project a runnable inputs template for a selected pipe.

Re-surfaces the input renderer (`input_renderer`) over one pipe of the resolved closure: the Smart
Inputs light shape by default, `--explicit` for the ceremonial `{concept, content}` envelope. The pipe
is selected by qualified `--pipe` ref and defaults to the closure's declared `main_pipe`. The crate
loader leaves the library open and current, so the live pipe is rendered directly.

See the codegen spec -> "CLI: codegen".
"""

from pathlib import Path
from typing import Annotated

import typer
from posthog import tag

from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME, DEFAULT_INPUTS_TOML_FILE_NAME
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.commands.crate_loading import load_normalized_crate_or_exit
from pipelex.cli.error_handlers import ErrorContext
from pipelex.interpreter_hub import get_required_pipe
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat, NoInputsRequiredError, render_inputs, render_inputs_toml
from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_telemetry_manager
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import ensure_directory_for_file_path, save_text_to_path
from pipelex.tools.misc.package_utils import get_package_version

COMMAND = "codegen"
SUB_COMMAND = "inputs"


def codegen_inputs_cmd(
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", "-p", help="Qualified pipe ref (domain.pipe_code). Defaults to the closure's main_pipe."),
    ] = None,
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Directories of .mthds bundles to resolve into the closure (added to --library-dir)."),
    ] = None,
    template_format: Annotated[
        InputsTemplateFormat,
        typer.Option("--format", "-f", help="Inputs template encoding (json or toml)."),
    ] = InputsTemplateFormat.JSON,
    explicit: Annotated[
        bool,
        typer.Option("--explicit", help="Emit the ceremonial {concept, content} envelope instead of the light values."),
    ] = False,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to write the inputs template (defaults to results/)."),
    ] = None,
    library_dir: Annotated[
        list[Path] | None,
        typer.Option("--library-dir", "-L", help="Directory of .mthds bundles to load (repeatable)."),
    ] = None,
) -> None:
    """Project a runnable inputs template for the selected (or main) pipe of the closure."""
    # needs_model_specs=True (like `validate`): library validation checks pipe model pins
    # against the deck, so the specs must be loaded even though codegen needs no inference.
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} {SUB_COMMAND}")

            combined_dirs: list[Path] = [*(paths or []), *(library_dir or [])]
            crate = load_normalized_crate_or_exit(library_dirs=combined_dirs or None)

            pipe_ref = pipe or _default_main_pipe_ref(crate=crate)
            try:
                the_pipe = get_required_pipe(pipe_code=pipe_ref)
            except PipeLibraryError as exc:
                typer.secho(f"Cannot project inputs — pipe '{pipe_ref}' not found:\n{exc}", fg=typer.colors.RED, err=True)
                raise typer.Exit(1) from exc

            try:
                content, default_file_name = _render(the_pipe=the_pipe, template_format=template_format, explicit=explicit)
            except NoInputsRequiredError as exc:
                typer.secho(str(exc), fg=typer.colors.YELLOW)
                raise typer.Exit(0) from exc

            destination = Path(output).expanduser() if output else Path("results") / default_file_name
            # Write-if-changed, like `codegen types`: no mtime churn and a truthful console verdict
            # when the committed template is already current.
            if destination.is_file() and destination.read_text(encoding="utf-8") == content:
                typer.secho(f"Unchanged {destination}", fg=typer.colors.BLUE)
            else:
                ensure_directory_for_file_path(file_path=destination)
                save_text_to_path(text=content, path=destination)
                typer.secho(f"Generated {destination}", fg=typer.colors.GREEN)
    finally:
        Pipelex.teardown_if_needed()


def _render(*, the_pipe: PipeAbstract, template_format: InputsTemplateFormat, explicit: bool) -> tuple[str, str]:
    """Render the inputs template string and return it with the format's default file name."""
    match template_format:
        case InputsTemplateFormat.JSON:
            return render_inputs(the_pipe, explicit=explicit), DEFAULT_INPUTS_FILE_NAME
        case InputsTemplateFormat.TOML:
            return render_inputs_toml(the_pipe, explicit=explicit), DEFAULT_INPUTS_TOML_FILE_NAME


def _default_main_pipe_ref(*, crate: LibraryCrate) -> str:
    """The closure's single declared `main_pipe` (qualified), or exit 1 if none / ambiguous."""
    candidates = [f"{domain_code}.{domain.main_pipe}" for domain_code, domain in crate.domains.items() if domain.main_pipe]
    if not candidates:
        typer.secho("Cannot project inputs — no main_pipe is declared in the closure; pass --pipe.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    if len(candidates) > 1:
        joined = ", ".join(sorted(candidates))
        typer.secho(f"Cannot project inputs — the closure declares several main_pipes ({joined}); pass --pipe.", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    return candidates[0]
