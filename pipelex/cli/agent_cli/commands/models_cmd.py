"""Agent CLI models command -- list available model presets, aliases, and waterfalls."""

from typing import Annotated

import typer

from pipelex.builder.operations.models_ops import ModelCategory, format_models_markdown, list_models
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import CliOutputFormat, agent_error, agent_success
from pipelex.pipelex import Pipelex


def agent_models_cmd(
    ctx: typer.Context,
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
        typer.Option("--format", help="Output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
) -> None:
    """List available model presets, aliases, and waterfalls.

    Outputs model configuration that an agent needs to reference when building pipelines.
    Default output is markdown; use --format json for structured JSON.
    """
    try:
        make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=backend is not None)

        result = list_models(categories=model_type, backend=backend)

        match output_format:
            case CliOutputFormat.JSON:
                agent_success({"success": True, **result})
            case CliOutputFormat.MARKDOWN:
                print(format_models_markdown(result))
    except SystemExit:
        # agent_error already handled and called sys.exit
        raise
    except Exception as exc:  # noqa: BLE001
        agent_error(f"Failed to list models: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
