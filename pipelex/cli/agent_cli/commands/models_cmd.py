"""Agent CLI models command -- list available model presets, aliases, and talent mappings."""

from typing import Annotated, Any

import typer

from pipelex.builder.operations.models_ops import ModelCategory, list_models
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success
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
) -> None:
    """List available model presets, aliases, waterfalls, and talent mappings.

    Outputs structured JSON to stdout with all model configuration
    that an agent needs to reference when building pipelines.
    """
    try:
        make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"], needs_inference=False, needs_model_specs=backend is not None)

        result: dict[str, Any] = list_models(categories=model_type, backend=backend)
        result["success"] = True
        result["talent_mappings_usage_hint"] = (
            "Use the talent name (key) as the value for llm_talent / extract_talent / img_gen_talent / search_talent"
            " in pipe specs passed to 'pipelex-agent pipe --spec'"
        )

        agent_success(result)
    except SystemExit:
        # agent_error already handled and called sys.exit
        raise
    except Exception as exc:
        agent_error(f"Failed to list models: {exc}", type(exc).__name__, cause=exc)
    finally:
        Pipelex.teardown_if_needed()
