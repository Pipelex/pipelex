"""Agent CLI codegen types command — project the crate's concept set into typed artifacts.

Same engine as the bare `pipelex codegen types` (resolve the closure into a normalized crate, emit
the types projection, write stamped files + `codegen.lock` through the write-if-changed layer), with
the agent CLI's presentation: a structured success envelope (markdown default, `--format json`) on
stdout and the structured error envelope on stderr. The resolve verdict maps to the 0/1/2 exit
policy — `1` invalid library (negative verdict), `2` closure not assembled (no verdict).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import typer

from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import (
    CliOutputFormat,
    agent_error,
    agent_success_formatted,
    set_agent_cli_error_format,
)
from pipelex.cli.commands.crate_loading import load_normalized_crate
from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.libraries.exceptions import LibraryLoadingError
from pipelex.libraries.pipe.exceptions import PipeLibraryError
from pipelex.pipelex import Pipelex
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pipelex.libraries.library_crate import LibraryCrate


def agent_codegen_types_cmd(
    target: Annotated[
        CodegenTarget,
        typer.Option("--target", "-t", help="Codegen target flavor (ts-zod, python-pydantic, python-structures)"),
    ],
    paths: Annotated[
        list[Path] | None,
        typer.Argument(help="Directories of .mthds bundles to resolve into the closure (added to --library-dir)"),
    ] = None,
    output_dir: Annotated[
        str,
        typer.Option("--output", "-o", help="Directory the generated files are written into (default: current directory)"),
    ] = ".",
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory of .mthds bundles to load (repeatable)"),
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
    """Project the crate's concept set into typed artifacts for the chosen target.

    Resolves the bundle closure into a normalized library crate, emits the types projection, and
    writes stamped files plus `codegen.lock` (write-if-changed; stale stamped files are pruned).

    Examples:
        pipelex-agent codegen types ./my_pipes/ --target python-pydantic
        pipelex-agent codegen types ./my_pipes/ --target ts-zod -o ./generated/
        pipelex-agent codegen types --target python-structures -L ./shared_pipes/ --format json
    """
    set_agent_cli_error_format(error_format or output_format)
    output_root = Path(output_dir).expanduser()
    # needs_model_specs=True (like `validate`): library validation checks pipe model pins
    # against the deck, so the specs must be loaded even though codegen needs no inference.
    make_pipelex_for_agent_cli(needs_inference=False, needs_model_specs=True)

    try:
        combined_dirs: list[Path] = [*(paths or []), *(Path(lib_dir) for lib_dir in library_dir or [])]

        crate: LibraryCrate
        try:
            crate = load_normalized_crate(library_dirs=combined_dirs or None)
        except (LibraryLoadingError, PipeLibraryError) as exc:
            # Negative verdict: the library is structurally invalid, so no crate can be produced.
            agent_error(f"Cannot resolve — the library is invalid: {exc}", error_type=type(exc).__name__, cause=exc, exit_code=1)
        except FileNotFoundError as exc:
            # No verdict: the closure could not even be assembled.
            agent_error(f"Cannot resolve — {exc}", error_type="FileNotFoundError", cause=exc, exit_code=2)

        emitted = emit_types(crate, target=target)
        report = write_stamped_projection(
            emitted,
            output_dir=output_root,
            crate_fingerprint=crate.fingerprint,
            engine_version=get_package_version(),
            kind=CodegenKind.TYPES,
            target=target,
        )
        result: dict[str, Any] = {
            "success": True,
            "kind": str(CodegenKind.TYPES),
            "target": str(target),
            "output_dir": str(output_root),
            "crate_fingerprint": crate.fingerprint,
            "engine_version": get_package_version(),
            "written": report.written,
            "unchanged": report.unchanged,
            "removed": report.removed,
            "lock_file": str(output_root / report.lock_path),
        }
        agent_success_formatted(result, markdown_renderer=_format_codegen_types_markdown, output_format=output_format)

    except typer.Exit:
        raise

    except Exception as exc:  # ruff: ignore[blind-except]
        # Agent CLI command boundary: agent_error() (NoReturn) converts any unexpected failure into the structured error payload.
        agent_error(str(exc), error_type=type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()


def _format_codegen_types_markdown(result: dict[str, Any]) -> str:
    """Render the codegen-types success envelope as agent-readable markdown."""
    lines: list[str] = [
        "# Codegen complete",
        "",
        f"- **Projection:** {result['kind']} → {result['target']}",
        f"- **Output directory:** {result['output_dir']}",
        f"- **Crate fingerprint:** `{result['crate_fingerprint']}`",
        "",
        "## Files",
        "",
    ]
    for filename in result["written"]:
        lines.append(f"- Generated `{filename}`")
    for filename in result["unchanged"]:
        lines.append(f"- Unchanged `{filename}`")
    for filename in result["removed"]:
        lines.append(f"- Removed stale `{filename}`")
    lines.append(f"- Locked `{result['lock_file']}`")
    return "\n".join(lines)
