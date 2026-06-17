"""Agent CLI inputs bundle command - generate example inputs from a bundle file or directory."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.builder.conventions import DEFAULT_BUNDLE_FILE_NAME
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.cli.agent_cli.commands.inputs._inputs_core import inputs_core
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import NoInputsRequiredError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError


def inputs_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to get inputs for (overrides bundle's main_pipe)"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Generate example input JSON from a bundle file (.mthds) or pipeline directory.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent inputs bundle my_bundle.mthds
        pipelex-agent inputs bundle my_bundle.mthds --pipe my_pipe
        pipelex-agent inputs bundle pipeline_01/
        pipelex-agent inputs bundle pipeline_01/ --pipe my_pipe
    """
    bundle_path: str | None = None
    target_path = Path(path)

    if target_path.is_dir():
        # Directory mode: auto-detect bundle file
        bundle_file = target_path / DEFAULT_BUNDLE_FILE_NAME
        if bundle_file.is_file():
            bundle_path = str(bundle_file)
        else:
            mthds_files = list(target_path.glob(f"*{MTHDS_EXTENSION}"))
            if len(mthds_files) == 0:
                agent_error(f"No .mthds bundle file found in directory '{path}'", error_type="FileNotFoundError")
            if len(mthds_files) > 1:
                mthds_names = ", ".join(mthds_file.name for mthds_file in mthds_files)
                agent_error(
                    f"Multiple .mthds files found in '{path}' ({mthds_names}) and no '{DEFAULT_BUNDLE_FILE_NAME}'. "
                    f"Pass the .mthds file directly instead.",
                    error_type="ArgumentError",
                )
            bundle_path = str(mthds_files[0])

        # Add directory as library dir
        target_dir_str = str(target_path)
        if library_dir is None:
            library_dir = [target_dir_str]
        elif target_dir_str not in library_dir:
            library_dir = [target_dir_str, *library_dir]

    elif is_pipelex_file(target_path):
        bundle_path = path
    else:
        agent_error(
            f"'{path}' is not a .mthds file or directory. "
            f"Use 'inputs pipe <code>' for pipe codes, or 'inputs bundle <path>' for .mthds files/directories.",
            error_type="ArgumentError",
        )

    pipe_code: str | None = pipe
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
    make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(inputs_core(pipe_code=pipe_code, bundle_path=Path(bundle_path), library_dirs=library_dirs))  # type: ignore[arg-type]
        agent_success(result)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", error_type="FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            extra["dry_run_error"] = exc.dry_run_error_message
        agent_error(exc.message, error_type="ValidateBundleError", cause=exc, **extra)

    except NoInputsRequiredError as exc:
        agent_success(
            {
                "success": True,
                "pipe_code": pipe_code,
                "inputs": {},
                "message": str(exc),
            }
        )

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

    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
