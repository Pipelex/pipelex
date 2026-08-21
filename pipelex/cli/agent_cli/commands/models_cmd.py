"""Agent CLI models command -- list available model presets, aliases, and waterfalls."""

from typing import Annotated

import typer

from pipelex.builder.operations.models_ops import ModelCategory, format_models_markdown, list_models
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success, set_agent_cli_error_format
from pipelex.pipelex import Pipelex


def agent_models_cmd(
    model_type: Annotated[
        list[ModelCategory] | None,
        typer.Option("--type", "-t", help="Filter by model category (repeatable): llm, extract, img_gen, search"),
    ] = None,
    backend: Annotated[
        str | None,
        typer.Option("--backend", "-b", help="Filter by backend name"),
    ] = None,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """List available model presets, aliases, and waterfalls.

    Outputs model configuration that an agent needs to reference when building pipelines.
    Default output is markdown; use --format json for structured JSON.
    """
    set_agent_cli_error_format(error_format or output_format)
    try:
        make_pipelex_for_agent_cli(needs_inference=False, needs_model_specs=backend is not None)

        result = list_models(categories=model_type, backend=backend)

        match output_format:
            case CliOutputFormat.JSON:
                agent_success({"success": True, **result})
            case CliOutputFormat.MARKDOWN:
                print(format_models_markdown(result))
    except (SystemExit, typer.Exit):
        # `agent_error` has already emitted the envelope and is on its way out. `typer.Exit` is a
        # `RuntimeError`, *not* a `SystemExit`, so leaving it out of this arm dropped it into the
        # broad catch below and printed a second envelope after the first — stderr then held two
        # JSON documents and a machine consumer parsing it got "Extra data".
        raise
    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(f"Failed to list models: {exc}", error_type=type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
