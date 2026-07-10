"""Agent CLI codegen check command — the offline drift check.

Same pure-hashing core as the bare `pipelex codegen check` (no Pipelex boot, no network, no API
key), with the agent CLI's presentation: an up-to-date verdict is a structured success envelope on
stdout; drift is a produced **negative verdict** — a structured error envelope on stderr carrying
the drifting artifacts, exit `1` (mirroring the validate surface); a missing or unreadable
`codegen.lock` is a no-verdict condition, exit `2`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    set_agent_cli_error_format,
)
from pipelex.codegen.check import run_codegen_check
from pipelex.codegen.exceptions import CodegenLockError
from pipelex.codegen.lock import CODEGEN_LOCK_FILENAME


def agent_codegen_check_cmd(
    root: Annotated[
        str,
        typer.Argument(help=f"Directory holding the {CODEGEN_LOCK_FILENAME} and generated artifacts (default: current directory)"),
    ] = ".",
    output_format: Annotated[
        CliOutputFormat,
        typer.Option("--format", help="Success output format: markdown (default) or json (structured)"),
    ] = CliOutputFormat.MARKDOWN,
    error_format: Annotated[
        CliOutputFormat | None,
        typer.Option("--error-format", help="Error output format (defaults to --format value): markdown or json"),
    ] = None,
) -> None:
    """Verify generated artifacts are current, offline — no engine, no network, no API key.

    Examples:
        pipelex-agent codegen check ./generated/
        pipelex-agent codegen check ./generated/ --format json
    """
    set_agent_cli_error_format(error_format or output_format)
    root_path = Path(root)

    try:
        report = run_codegen_check(root=root_path)

        if not report.lock_found:
            agent_error(
                f"No {CODEGEN_LOCK_FILENAME} found in '{root_path}' — nothing to check.",
                error_type="CodegenLockNotFoundError",
                exit_code=2,
                root=str(root_path),
            )

        if not report.is_current:
            # Produced negative verdict: the artifacts have drifted (exit 1, like an invalid validate).
            drifts = [drift.model_dump(mode="json") for drift in report.drifts]
            agent_error(
                f"Generated artifacts in '{root_path}' have drifted.",
                error_type="CodegenDriftError",
                exit_code=1,
                root=str(root_path),
                is_current=False,
                drifts=drifts,
            )

        result: dict[str, Any] = {
            "success": True,
            "is_current": True,
            "root": str(root_path),
        }
        agent_success_formatted(result, markdown_renderer=_format_codegen_check_markdown, output_format=output_format)

    except typer.Exit:
        raise

    except CodegenLockError as exc:
        # No verdict: the lock exists but cannot be read, so nothing can be checked.
        agent_error(exc.message, error_type=type(exc).__name__, cause=exc, exit_code=2, root=str(root_path))

    except Exception as exc:  # noqa: BLE001
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)


def _format_codegen_check_markdown(result: dict[str, Any]) -> str:
    """Render the codegen-check success envelope as agent-readable markdown."""
    return "\n".join(
        [
            "# Generated artifacts up to date",
            "",
            f"Generated artifacts in `{result['root']}` match their `{CODEGEN_LOCK_FILENAME}` — no drift.",
        ]
    )
