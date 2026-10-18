"""Agent CLI fix bundle command."""

import asyncio
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_argument_error,
    agent_error,
    agent_error_fix_bundle,
    agent_file_error,
    agent_success_formatted,
    agent_unreadable_file_error,
    use_agent_cli_error_format,
)
from pipelex.cli.agent_cli.commands.bundle_path_resolver import resolve_bundle_target
from pipelex.cli.judged_target import fix_judged_target
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.fixes.fix_loop import FixBundleResult, unfixable_method_result
from pipelex.pipeline.fixes.fix_render import format_fix_markdown
from pipelex.pipeline.fixes.planner import KNOWN_FIX_CODES


def _normalize_rule_codes(codes: list[str] | None) -> tuple[str, ...] | None:
    if not codes:
        return None
    return tuple(codes)


def _reject_invalid_rule_filters(*, select_codes: tuple[str, ...] | None, ignore_codes: tuple[str, ...] | None) -> None:
    if select_codes is not None and ignore_codes is not None:
        agent_argument_error(
            "--select and --ignore are mutually exclusive",
            argument="--ignore",
            reason="contradicts --select",
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
        agent_argument_error(
            f"Unknown fix rule code(s): {unknown}. Known codes: {known_codes}",
            argument=unknown,
            reason="unknown fix rule code",
            exit_code=2,
            unknown_fix_codes=unknown_codes,
            known_fix_codes=sorted(KNOWN_FIX_CODES),
        )


def _result_payload(result: FixBundleResult, *, bundle_path: str) -> dict[str, Any]:
    return {
        "bundle_path": str(Path(bundle_path).resolve()),
        # The remaining errors' codes are the problem's items' when the fix fails, never a member of the result.
        **result.model_dump(mode="json", exclude_none=True, exclude={"remaining_error_codes"}),
    }


def _failure_message(result: FixBundleResult) -> str:
    message = (
        f"Fix loop stopped after {result.iterations} iteration(s): "
        f"{len(result.fixes_applied)} fix(es) applied, {len(result.remaining_errors)} error(s) remaining"
    )
    if result.bail_reason is not None:
        message = f"{message}; {result.bail_reason}"
    return message


def _emit_still_invalid(*, result: FixBundleResult, bundle_path: str) -> NoReturn:
    """Report the still-invalid verdict, format-aware, and exit 1.

    The problem is the method's that does not validate, its faults the remaining errors.
    """
    agent_error_fix_bundle(result=result, bundle_path=str(Path(bundle_path).resolve()), message=_failure_message(result))


def fix_bundle_cmd(
    path: Annotated[
        str,
        typer.Argument(help="Path to a .mthds bundle file, or a method's folder, whose every bundle is judged"),
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
        typer.Option("--error-format", help="Error output format: markdown or json (defaults to the program's --error-format, then to --format)"),
    ] = None,
) -> None:
    """Fix a bundle file (.mthds) or a method's folder in place.

    A folder is judged whole, every bundle of its method tree, as `validate bundle` judges it.
    """
    use_agent_cli_error_format(error_format=error_format, output_format=output_format)

    select_codes = _normalize_rule_codes(select_codes_raw)
    ignore_codes = _normalize_rule_codes(ignore_codes_raw)
    _reject_invalid_rule_filters(select_codes=select_codes, ignore_codes=ignore_codes)

    # A folder is judged whole, every bundle of its method tree, as `validate bundle` judges it. A folder whose tree is
    # refused is the still-invalid verdict, with nothing to fix, as `validate bundle` gives it the invalid one.
    try:
        target = resolve_bundle_target(path, library_dir=library_dir)
    except ValidateBundleError as exc:
        _emit_still_invalid(result=unfixable_method_result(error=exc), bundle_path=str(Path(path).expanduser()))
    bundle_path = str(target.judged_path)
    library_dirs = target.library_dirs

    try:
        make_pipelex_for_agent_cli(library_dirs=library_dirs, needs_inference=False)
        result = asyncio.run(
            fix_judged_target(
                target=target,
                writable_library_dirs=None,
                allow_signatures=allow_signatures,
                max_iterations=max_iterations,
                select_codes=select_codes,
                ignore_codes=ignore_codes,
            )
        )
        if result.is_valid:
            payload = _result_payload(result, bundle_path=bundle_path)
            agent_success_formatted({"success": True, **payload}, markdown_renderer=format_fix_markdown, output_format=output_format)
            if not allow_signatures and result.is_runnable is False:
                raise typer.Exit(1)
            return

        # Still-invalid verdict: the problem of the method that does not validate, its faults the remaining errors.
        _emit_still_invalid(result=result, bundle_path=bundle_path)

    except FileNotFoundError as exc:
        agent_file_error(f"Bundle file not found: {bundle_path}", path=bundle_path, reason="not found", cause=exc, exit_code=2)

    except OSError as exc:
        # A method file the loop could not read; a write it could not make is a `FixWriteFailedError`, never an OSError.
        agent_unreadable_file_error(error=exc, path=bundle_path, exit_code=2)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
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
        agent_error(exc.message, cause=exc, exit_code=2, **availability_extra)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into its problem.
        agent_error(str(exc), cause=exc, exit_code=2)

    finally:
        Pipelex.teardown_if_needed()
