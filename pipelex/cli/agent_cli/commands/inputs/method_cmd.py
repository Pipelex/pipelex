"""Agent CLI inputs method command - generate example inputs for an installed method."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import emit_inputs_result, emit_no_inputs_result, inputs_core
from pipelex.cli.method_resolver import resolve_method_target
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_machinery.rendering.input_renderer import InputsTemplateFormat
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError


def inputs_method_cmd(
    name: Annotated[
        str,
        typer.Argument(help="Name of the installed method"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code (overrides method's main_pipe)"),
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
    """Generate an example inputs template for an installed method.

    Resolves the method by name, finds its .mthds bundle, and generates inputs.
    Outputs the JSON envelope (or raw TOML with --format toml) to stdout on
    success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs method my-method
        pipelex-agent inputs method my-method --pipe custom_pipe
        pipelex-agent inputs method my-method --format toml
        pipelex-agent inputs method my-method --explicit
    """
    pipe_code, method_library_dirs, method = resolve_method_target(
        method_name=name,
        pipe_override=pipe,
        library_dirs=library_dir,
    )
    bundle_path: Path | None = None
    if method.mthds_files:
        bundle_path = method.mthds_files[0]

    # Merge library dirs: method dirs first, then user-specified
    library_dirs_paths = [Path(lib_dir) for lib_dir in method_library_dirs]
    if library_dir:
        library_dirs_paths.extend(Path(lib_dir) for lib_dir in library_dir)

    make_pipelex_for_agent_cli(library_dirs=library_dirs_paths, needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(inputs_core(pipe_code=pipe_code, bundle_path=bundle_path, library_dirs=library_dirs_paths, explicit=explicit))
        emit_inputs_result(result, template_format=template_format, explicit=explicit)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", error_type="FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            extra["dry_run_error"] = exc.dry_run_error_message
        agent_error(exc.message, error_type="ValidateBundleError", cause=exc, **extra)

    except NoInputsRequiredError as exc:
        emit_no_inputs_result(pipe_code=pipe_code, message=str(exc), template_format=template_format)

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

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
