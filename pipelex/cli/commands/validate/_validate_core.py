from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer
from posthog import tag
from rich.traceback import Traceback

from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
    handle_signatures_not_allowed_error,
    handle_validate_bundle_error,
)
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.hub import (
    get_console,
    get_library_manager,
    get_pipes,
    get_required_pipe,
    get_telemetry_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipe_signature.signature_walk import collect_signature_refs
from pipelex.pipelex import Pipelex
from pipelex.pipeline.bundle_validator import BundleValidator
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.execution_seams import load_libraries_and_activate
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.package_utils import get_package_version

if TYPE_CHECKING:
    from pathlib import Path

COMMAND = "validate"


def _format_signatures_summary_suffix(signature_count: int) -> str:
    """Return the suffix appended to lenient-mode validation summaries.

    Empty when no signatures were involved so fully-implemented bundles read naturally.
    """
    if signature_count == 0:
        return ""
    if signature_count == 1:
        return " (1 signature)"
    return f" ({signature_count} signatures)"


def do_validate_all_libraries_and_dry_run(
    library_dirs: list[Path] | None = None,
    *,
    allow_signatures: bool = False,
) -> None:
    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} all")

            # Single public composer for the open/set/load ceremony — leaves the library loaded and
            # current for the sweep below, owning the standard 3-tier dir resolution and load-failure
            # teardown. No teardown on success here: the caller (validate_pipe_cmd) owns Pipelex teardown.
            load_libraries_and_activate(library_dirs)

            # The pipe list is needed only to render the "Validating N" line and the signature-count
            # suffix; validate_current_library re-derives it (with the same strict-mode signature filter)
            # from the current library for the sweep itself.
            all_pipes = get_pipes()
            pipes = all_pipes if allow_signatures else [pipe for pipe in all_pipes if not pipe.is_signature]
            if library_dirs:
                dirs_str = ", ".join(f'"{lib_dir}"' for lib_dir in library_dirs)
                typer.echo(f"Validating {len(pipes)} pipe(s) from: {dirs_str}")

            # validate_current_library owns the static wiring pass, the strict signature pre-pass, and the
            # single PIPE_DRY_RUN telemetry event — sweeping the library we just loaded, without teardown.
            asyncio.run(BundleValidator().validate_current_library(allow_signatures=allow_signatures))
            signature_count = sum(1 for pipe in pipes if pipe.is_signature)
            typer.echo(f"Setup sequence passed OK, config and pipelines are validated.{_format_signatures_summary_suffix(signature_count)}")
    except SignaturesNotAllowedError as sig_error:
        # A non-signature pipe in the library reaches a PipeSignature. Render it as a friendly
        # CLI error (matching the bundle/pipe paths) instead of bubbling a raw traceback.
        handle_signatures_not_allowed_error(sig_error, context=ErrorContext.VALIDATION)
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)


async def _validate_pipe_or_bundle(
    pipe_code: str | None = None,
    *,
    bundle_path: Path | None = None,
    library_dirs: list[Path] | None = None,
    allow_signatures: bool = False,
) -> None:
    """Core async validation logic shared between method and pipe subcommands."""
    if bundle_path:
        try:
            bundle_result = await validate_bundle(
                mthds_file_path=bundle_path,
                library_dirs=library_dirs,
                allow_signatures=allow_signatures,
            )
            signature_count = sum(1 for pipe in bundle_result.pipes if pipe.is_signature)
            typer.secho(
                f"Successfully validated bundle '{bundle_path}'{_format_signatures_summary_suffix(signature_count)}",
                fg=typer.colors.GREEN,
            )
        except FileNotFoundError as exc:
            get_console().print(Traceback())
            typer.secho(
                f"Failed to load bundle '{bundle_path}':",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(1) from exc
        except ValidateBundleError as bundle_error:
            handle_validate_bundle_error(bundle_error, bundle_path=bundle_path)
    elif pipe_code:
        library_manager = get_library_manager()
        library_id, _ = library_manager.open_library()
        set_current_library(library_id=library_id)
        effective_dirs, _ = resolve_library_dirs(library_dirs)

        if effective_dirs:
            library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

        pipe = get_required_pipe(pipe_code=pipe_code)
        typer.echo(f"Validating pipe '{pipe_code}'...")
        try:
            await BundleValidator().validate_pipes(
                pipes=[pipe],
                library_id=library_id,
                allow_signatures=allow_signatures,
            )
        except SignaturesNotAllowedError as sig_error:
            handle_signatures_not_allowed_error(sig_error, context=ErrorContext.VALIDATION)
        signature_count = len(collect_signature_refs(pipe=pipe))
        typer.secho(
            f"Successfully validated pipe '{pipe_code}'{_format_signatures_summary_suffix(signature_count)}",
            fg=typer.colors.GREEN,
        )
    else:
        typer.secho(
            "Failed to validate: no pipe code or bundle specified",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1)


def execute_validate(
    pipe_code: str | None,
    *,
    bundle_path: Path | None,
    library_dirs: list[Path] | None,
    telemetry_command_label: str = COMMAND,
    allow_signatures: bool = False,
    temporal: bool | None = None,
) -> None:
    """Synchronous entry point wrapping the async validation with Pipelex setup/teardown.

    ``temporal`` overrides ``temporal.is_enabled`` for the boot (mirroring ``run``). The
    validation sweep itself always runs in-process — under a Temporal-enabled hub it scopes
    its own in-process router so nested controller sub-pipes do not dispatch to Temporal — so
    this flag does not change *what* validation does; it controls how Pipelex boots, which is
    the lever for exercising the "validation stays in-process on a Temporal backend" contract.
    """
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True, temporal_enabled=temporal)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            if bundle_path:
                tag(name=EventProperty.CLI_COMMAND, value=f"{telemetry_command_label} bundle")
            else:
                tag(name=EventProperty.CLI_COMMAND, value=f"{telemetry_command_label} pipe")

            asyncio.run(
                _validate_pipe_or_bundle(
                    pipe_code=pipe_code,
                    bundle_path=bundle_path,
                    library_dirs=library_dirs,
                    allow_signatures=allow_signatures,
                )
            )
    except PipeNotFoundError as exc:
        error_message = str(exc)
        if pipe_code == "all":
            error_message += "\nDid you mean 'pipelex validate --all'?"
        typer.secho(
            f"Failed to validate: {error_message}",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(1) from exc
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)
    finally:
        Pipelex.teardown_if_needed()
