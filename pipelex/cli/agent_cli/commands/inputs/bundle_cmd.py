"""Agent CLI inputs bundle command - generate example inputs from a bundle file or directory."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import typer

from pipelex.base_exceptions import PipelexConfigError
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli, report_agent_init_failure
from pipelex.cli.agent_cli.commands.agent_output import agent_error, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import emit_inputs_result, inputs_core
from pipelex.cli.bundle_target_resolution import BundleTargetResolutionError, FolderReading, resolve_bundle_target_core
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import MethodEntryError, ValidateBundleError


def inputs_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, which starts at its entry pipe unless --pipe names one"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to get inputs for (overrides bundle's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
    template_format: Annotated[
        InputsTemplateFormat,
        typer.Option("--format", help="Inputs template format: 'json' for the JSON result envelope (default), 'toml' for raw TOML on stdout"),
    ] = InputsTemplateFormat.JSON,
    explicit: Annotated[
        bool,
        typer.Option("--explicit", help="Emit the ceremonial {concept, content} envelope form instead of the light values"),
    ] = False,
) -> None:
    """Generate an example inputs template from a bundle file (.mthds) or pipeline directory.

    Outputs the JSON envelope (or raw TOML with --format toml) to stdout on
    success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs bundle my_bundle.mthds
        pipelex-agent inputs bundle my_bundle.mthds --pipe my_pipe
        pipelex-agent inputs bundle pipeline_01/
        pipelex-agent inputs bundle pipeline_01/ --pipe my_pipe
        pipelex-agent inputs bundle pipeline_01/ --format toml
        pipelex-agent inputs bundle pipeline_01/ --explicit
    """
    # A folder is read as its method tree: the pipe is the one named, else the one the method starts at, as `run bundle`
    # reads it. A folder whose pipe was named loads as the method's library, with no entry bundle, as `run bundle` runs it.
    try:
        target = resolve_bundle_target_core(path, library_dir=library_dir, reading=FolderReading.ENTRY_PIPE, pipe_override=pipe)
    except MethodEntryError as exc:
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc)
    except ValidateBundleError as exc:
        agent_error(exc.message, error_type="ValidateBundleError", cause=exc, validation_errors=extract_validation_errors(exc))
    except PipelexConfigError as exc:
        # Listing the tree reads its limits from the configuration, before the boot would.
        report_agent_init_failure(error=exc)
    if isinstance(target, BundleTargetResolutionError):
        agent_error(
            f"'{path}' is not a .mthds file or directory. "
            f"Use 'inputs pipe <code>' for pipe codes, or 'inputs bundle <path>' for .mthds files/directories.",
            error_type="ArgumentError",
        )
    bundle_path = target.bundle_path
    library_dirs = target.library_dirs
    make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False)

    try:
        result = asyncio.run(inputs_core(pipe_code=target.pipe_code, bundle_path=bundle_path, library_dirs=library_dirs, explicit=explicit))
        emit_inputs_result(result, template_format=template_format, explicit=explicit)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", error_type="FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        # A failing dry run rides validation_errors as one located dry_run item per failing pipe.
        agent_error(exc.message, error_type="ValidateBundleError", cause=exc, validation_errors=extract_validation_errors(exc))

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            error_type="PipeOperatorModelChoiceError",
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
        agent_error(exc.message, error_type="PipeOperatorModelAvailabilityError", cause=exc, **availability_extra)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
