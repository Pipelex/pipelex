"""Agent CLI build command - simplified pipe building with JSON output."""

import asyncio
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.build_core import BuildPipeError, build_pipe_core
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError

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
    ctx: typer.Context,
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
    Generates MTHDS bundle only (no inputs.json or runner.py).

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.
    """
    make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"])

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
        agent_success(result.to_agent_json())

    except BuildPipeError as exc:
        build_extra: dict[str, Any] = {}
        if exc.failure_memory_path:
            build_extra["failure_memory_path"] = str(exc.failure_memory_path)
        if exc.__cause__:
            build_extra["cause_type"] = type(exc.__cause__).__name__
            build_extra["cause_message"] = str(exc.__cause__)
        agent_error(exc.message, "BuildPipeError", cause=exc, **build_extra)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        validate_extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            validate_extra["dry_run_error"] = exc.dry_run_error_message
        if exc.failed_bundle_path:
            validate_extra["failed_bundle_path"] = exc.failed_bundle_path
        agent_error(exc.message, "ValidateBundleError", cause=exc, **validate_extra)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            "PipeOperatorModelChoiceError",
            cause=exc,
            pipe_code=exc.pipe_code,
            model_type=str(exc.model_type),
            model_choice=str(exc.model_choice),
        )

    except PipeOperatorModelAvailabilityError as exc:
        availability_extra: dict[str, Any] = {
            "pipe_code": exc.pipe_code,
            "model_handle": exc.model_handle,
        }
        if exc.fallback_list:
            availability_extra["fallback_list"] = exc.fallback_list
        if exc.pipe_stack:
            availability_extra["pipe_stack"] = exc.pipe_stack
        agent_error(exc.message, "PipeOperatorModelAvailabilityError", cause=exc, **availability_extra)

    except Exception as exc:
        agent_error(f"Build failed: {exc}", type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
