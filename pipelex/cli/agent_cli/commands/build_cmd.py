"""Agent CLI build command - simplified pipe building with JSON output."""

import asyncio
import json
import sys
from typing import Annotated

import typer

from pipelex.cli.agent_cli.commands.build_core import BuildPipeError, build_pipe_core
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import ErrorContext

AGENT_OUTPUT_DIR = "pipelex-wip"
AGENT_OUTPUT_NAME = "pipeline"

# Example commands:
#
# pipelex-agent build "Given a theme, write a Haiku"
# pipelex-agent build "Take a CV and a Job offer, analyze if they match"
# pipelex-agent build "Given an expense report, apply company rules"
# pipelex-agent build "Take a photo as input, and render the opposite of the photo"
#
# With a custom builder pipe:
# pipelex-agent build "Generate image prompts from a brief" --builder-pipe custom_builder


def build_cmd(
    prompt: Annotated[
        str,
        typer.Argument(help="Prompt describing what the pipeline should do"),
    ],
    builder_pipe: Annotated[
        str,
        typer.Option("--builder-pipe", help="Builder pipe to use for generating the pipeline"),
    ] = "pipe_builder",
) -> None:
    """Build a pipeline from a prompt and output JSON with paths.

    Outputs to pipelex-wip/ directory with incremental naming (pipeline_01, pipeline_02, etc.).
    Generates PLX bundle only (no inputs.json or runner.py).

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_PIPE)

    async def run_build():
        return await build_pipe_core(
            prompt=prompt,
            builder_pipe=builder_pipe,
            output_dir=AGENT_OUTPUT_DIR,
            output_name=AGENT_OUTPUT_NAME,
            generate_inputs=False,
        )

    try:
        result = asyncio.run(run_build())
        # Output JSON to stdout on success
        print(json.dumps(result.to_agent_json(), indent=2))

    except BuildPipeError as exc:
        # Output JSON to stderr on error
        error_json = {
            "error": True,
            "message": exc.message,
        }
        if exc.failure_memory_path:
            error_json["failure_memory_path"] = str(exc.failure_memory_path)
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc

    except Exception as exc:
        # Handle unexpected errors
        error_json = {
            "error": True,
            "message": f"Build failed: {exc}",
        }
        print(json.dumps(error_json, indent=2), file=sys.stderr)
        raise typer.Exit(1) from exc
