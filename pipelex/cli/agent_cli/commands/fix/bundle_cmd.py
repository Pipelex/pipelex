"""Agent CLI fix bundle command."""

import asyncio
import sys
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    get_agent_cli_error_format,
    set_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.fixes.fix_loop import FixBundleResult, fix_bundle_file
from pipelex.pipeline.fixes.fix_render import format_fix_markdown, format_fix_still_invalid_markdown
from pipelex.pipeline.fixes.planner import KNOWN_FIX_CODES


def _normalize_rule_codes(codes: list[str] | None) -> tuple[str, ...] | None:
    if not codes:
        return None
    return tuple(codes)


def _reject_invalid_rule_filters(*, select_codes: tuple[str, ...] | None, ignore_codes: tuple[str, ...] | None) -> None:
    if select_codes is not None and ignore_codes is not None:
        agent_error(
            "--select and --ignore are mutually exclusive",
            error_type="ArgumentError",
            exit_code=2,
            known_fix_codes=sorted(KNOWN_FIX_CODES),
        )

    requested_codes: set[str] = set()
    if select_codes is not None:
        requested_codes.update(select_codes)
    if ignore_codes is not None:
        requested_codes.update(ignore_codes)
    unknown_codes = sorted(requested_codes - KNOWN_FIX_CODES)
    if unknown_codes:
        known_codes = ", ".join(sorted(KNOWN_FIX_CODES))
        unknown = ", ".join(unknown_codes)
        agent_error(
            f"Unknown fix rule code(s): {unknown}. Known codes: {known_codes}",
            error_type="ArgumentError",
            exit_code=2,
            unknown_fix_codes=unknown_codes,
            known_fix_codes=sorted(KNOWN_FIX_CODES),
        )


def _result_payload(result: FixBundleResult, *, bundle_path: str) -> dict[str, Any]:
    return {
        "bundle_path": str(Path(bundle_path).resolve()),
        **result.model_dump(mode="json", exclude_none=True),
    }


def _failure_message(result: FixBundleResult) -> str:
    message = (
        f"Fix loop stopped after {result.iterations} iteration(s): "
        f"{len(result.fixes_applied)} fix(es) applied, {len(result.remaining_errors)} error(s) remaining"
    )
    if result.bail_reason is not None:
        message = f"{message}; {result.bail_reason}"
    return message


def fix_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file or a pipeline directory"),
    ],
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
    max_iterations: Annotated[
        int | None,
        typer.Option("--max-iterations", min=1, help="Maximum fix-apply rounds before reporting non-convergence"),
    ] = None,
    select_codes_raw: Annotated[
        list[str] | None,
        typer.Option("--select", help="Only apply the named fix rule code. Can be specified multiple times."),
    ] = None,
    ignore_codes_raw: Annotated[
        list[str] | None,
        typer.Option("--ignore", help="Skip the named fix rule code. Can be specified multiple times."),
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
    """Fix a bundle file (.mthds) or pipeline directory in place."""
    set_agent_cli_error_format(error_format or output_format)

    select_codes = _normalize_rule_codes(select_codes_raw)
    ignore_codes = _normalize_rule_codes(ignore_codes_raw)
    _reject_invalid_rule_filters(select_codes=select_codes, ignore_codes=ignore_codes)

    bundle_path, library_dir = resolve_bundle_target(path, library_dir=library_dir)
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None

    try:
        make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False, needs_model_specs=True)
        result = asyncio.run(
            fix_bundle_file(
                Path(bundle_path),
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
                max_iterations=max_iterations,
                select_codes=select_codes,
                ignore_codes=ignore_codes,
            )
        )
        payload = _result_payload(result, bundle_path=bundle_path)
        if result.is_valid:
            agent_success_formatted({"success": True, **payload}, markdown_renderer=format_fix_markdown, output_format=output_format)
            if not allow_signatures and result.is_runnable is False:
                raise typer.Exit(1)
            return

        # Still-invalid verdict: format-aware. JSON keeps the exact FixBundleError envelope (the result
        # fields + bail_reason via **payload); markdown renders the remaining errors as prose with their
        # 💡 lines (mirroring the human still-invalid panel) instead of a raw JSON dump of the details.
        match get_agent_cli_error_format():
            case CliOutputFormat.JSON:
                agent_error(_failure_message(result), error_type="FixBundleError", exit_code=1, **payload)
            case CliOutputFormat.MARKDOWN:
                print(format_fix_still_invalid_markdown(result, bundle_path=str(payload["bundle_path"])), file=sys.stderr)
                raise typer.Exit(1)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", error_type="FileNotFoundError", cause=exc, exit_code=2)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            error_type="PipeOperatorModelChoiceError",
            cause=exc,
            exit_code=2,
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
        agent_error(exc.message, error_type="PipeOperatorModelAvailabilityError", cause=exc, exit_code=2, **availability_extra)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc, exit_code=2)

    finally:
        Pipelex.teardown_if_needed()
