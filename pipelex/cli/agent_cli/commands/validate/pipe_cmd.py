"""Agent CLI validate pipe command - validate a pipe by code or all pipes with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    extract_validation_errors,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.validate._validate_core import (
    validate_all_core,
    validate_pipe_core,
)
from pipelex.cli.method_resolver import resolve_pipe_from_exports
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.mthds_parsing.helpers import MTHDS_EXTENSION, is_pipelex_file
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.exceptions import DryRunError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validation_render import format_validate_markdown


def validate_pipe_cmd(
    pipe_code: Annotated[
        str | None,
        typer.Argument(help="Pipe code to validate"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
    allow_signatures: Annotated[
        bool,
        typer.Option(
            "--allow-signatures",
            help="Accept PipeSignature placeholders in the dependency graph (lenient mode).",
        ),
    ] = False,
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Validate a pipe by code, or all pipes, and output the results.

    Default output is markdown; use --format json for structured JSON.
    Results go to stdout on success, errors to stderr with exit code 1.

    Examples:
        pipelex-agent validate pipe my_pipe
        pipelex-agent validate pipe --all
        pipelex-agent validate pipe --all -L ./my_pipes
        pipelex-agent validate pipe my_draft_pipe --allow-signatures
    """
    set_agent_cli_error_format(error_format or output_format)

    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    # Handle --all flag
    if validate_all:
        if pipe_code:
            agent_error("--all cannot be used with a pipe code", error_type="ArgumentError", exit_code=2)

        make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False, needs_model_specs=True)

        try:
            result = asyncio.run(validate_all_core(library_dirs=library_dirs, allow_signatures=allow_signatures))
            agent_success_formatted(result, markdown_renderer=format_validate_markdown, output_format=output_format)

            # Gate-from-report (D-B consumer-decides): `validate all` is strict by default — the
            # library is valid but NOT runnable while unsatisfied PipeSignature placeholders remain.
            # The success envelope (carrying library-wide pending_signatures + is_runnable) is emitted
            # above; the exit code reflects the gate. --allow-signatures tolerates them. Re-raised by
            # the `except typer.Exit` arm below so teardown still runs.
            if not allow_signatures and not result.get("is_runnable", True):
                raise typer.Exit(1)

        except ValidateBundleError as exc:
            # Invalid verdict: structured failure envelope. validation_errors[] is the shared builder's
            # output (a residual dry-run failure rides one dry_run item). Signatures are a runnability
            # fact (pending_signatures + the gate above), not an error, so they never reach this arm.
            agent_error(
                exc.message,
                error_type="ValidateBundleError",
                cause=exc,
                is_valid=False,
                validation_errors=extract_validation_errors(exc),
            )

        except PipeOperatorModelChoiceError as exc:
            agent_error(
                exc.message,
                error_type="PipeOperatorModelChoiceError",
                cause=exc,
                pipe_code=exc.pipe_code,
                model_type=str(exc.model_type),
                model_choice=str(exc.model_choice),
                exit_code=2,
            )

        except PipeOperatorModelAvailabilityError as exc:
            agent_error(
                str(exc),
                error_type="PipeOperatorModelAvailabilityError",
                cause=exc,
                pipe_code=exc.pipe_code,
                model_handle=exc.model_handle,
                exit_code=2,
            )

        except DryRunError as exc:
            # A dry-run failure is a produced NEGATIVE VERDICT (a pipe is invalid) — exit 1, NOT the
            # catch-all's no-verdict 2. `validate --all` sweeps via validate_current_library, which
            # raises DryRunError directly (not wrapped in ValidateBundleError as the bundle path is).
            agent_error(str(exc), error_type="DryRunError", cause=exc, is_valid=False, exit_code=1)

        except typer.Exit:
            # The runnability gate raises typer.Exit(1) after emitting the success envelope; let it
            # propagate (exit code) rather than be reshaped into an agent_error by the broad handler below.
            raise

        except Exception as exc:  # ruff: ignore[blind-except]
            # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
            agent_error(str(exc), error_type=type(exc).__name__, cause=exc, exit_code=2)

        finally:
            Pipelex.teardown_if_needed()
        return

    if not pipe_code:
        agent_error(
            "No pipe code specified. Use --all to validate all pipes, or use 'validate bundle <path>' for bundle files.",
            error_type="ArgumentError",
            exit_code=2,
        )

    # Helpful error if the user passes a path instead of a pipe code
    target_path = Path(pipe_code)
    if target_path.is_dir() or is_pipelex_file(target_path) or pipe_code.endswith(MTHDS_EXTENSION):
        agent_error(
            f"'{pipe_code}' looks like a file path or directory. "
            f"Use 'validate bundle {pipe_code}' for bundles/directories, or 'validate pipe <code>' for pipe codes.",
            error_type="ArgumentError",
            exit_code=2,
        )

    # Check installed methods' exports for additional library dirs
    try:
        export_dirs = resolve_pipe_from_exports(pipe_code)
    except ValueError as exc:
        agent_error(
            f"Ambiguous pipe code '{pipe_code}': {exc}",
            error_type="ArgumentError",
            cause=exc,
            exit_code=2,
        )
    if export_dirs:
        export_paths = [Path(export_dir) for export_dir in export_dirs]
        if library_dirs is None:
            library_dirs = export_paths
        else:
            library_dirs = [*export_paths, *library_dirs]

    make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False, needs_model_specs=True)

    try:
        result = asyncio.run(validate_pipe_core(pipe_code=pipe_code, library_dirs=library_dirs, allow_signatures=allow_signatures))
        agent_success_formatted(result, markdown_renderer=format_validate_markdown, output_format=output_format)

    except PipeNotFoundError as exc:
        error_message = str(exc)
        if pipe_code == "all":
            error_message += " Did you mean '--all'?"
        agent_error(error_message, error_type="PipeNotFoundError", cause=exc, exit_code=2)

    except ValidateBundleError as exc:
        # Invalid verdict (see the --all arm): structured failure envelope; validation_errors[] is the
        # shared builder's output (a residual dry-run failure rides one dry_run item).
        agent_error(
            exc.message,
            error_type="ValidateBundleError",
            cause=exc,
            is_valid=False,
            validation_errors=extract_validation_errors(exc),
        )

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            error_type="PipeOperatorModelChoiceError",
            cause=exc,
            pipe_code=exc.pipe_code,
            model_type=str(exc.model_type),
            model_choice=str(exc.model_choice),
            exit_code=2,
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
        agent_error(exc.message, error_type="PipeOperatorModelAvailabilityError", cause=exc, **availability_extra, exit_code=2)

    except DryRunError as exc:
        # A dry-run failure is a produced NEGATIVE VERDICT (the pipe is invalid) — exit 1, NOT the
        # catch-all's no-verdict 2. validate_pipe_core sweeps via validate_pipes, which raises
        # DryRunError directly (not wrapped in ValidateBundleError as the bundle path is).
        agent_error(str(exc), error_type="DryRunError", cause=exc, is_valid=False, exit_code=1)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc, exit_code=2)

    finally:
        Pipelex.teardown_if_needed()
