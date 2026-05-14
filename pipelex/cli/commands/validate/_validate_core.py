from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer
from posthog import tag
from rich.traceback import Traceback

from pipelex import log
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
    get_optional_pipe,
    get_required_pipe,
    get_telemetry_manager,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipe_signature.exceptions import SignaturesNotAllowedError
from pipelex.pipelex import Pipelex
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventName, EventProperty
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
    allow_signatures: bool = False,
) -> None:
    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=get_package_version())
            tag(name=EventProperty.CLI_COMMAND, value=f"{COMMAND} all")

            library_manager = get_library_manager()
            library_id, library = library_manager.open_library()
            set_current_library(library_id=library_id)
            effective_dirs, source_label = resolve_library_dirs(library_dirs)
            if effective_dirs:
                library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)
            else:
                log.info(f"No library directories to load ({source_label})")

            all_pipes = library.pipe_library.get_pipes()
            # In strict mode, signatures themselves are skipped (validating them would always fail
            # the signature pre-check). In lenient mode, iterate all pipes — signatures dry-run trivially.
            pipes = all_pipes if allow_signatures else [pipe for pipe in all_pipes if not pipe.is_signature]
            if library_dirs:
                dirs_str = ", ".join(f'"{lib_dir}"' for lib_dir in library_dirs)
                typer.echo(f"Validating {len(pipes)} pipe(s) from: {dirs_str}")
            for pipe in pipes:
                pipe.validate_with_libraries()

            get_telemetry_manager().track_event(EventName.PIPE_DRY_RUN, properties={EventProperty.NB_PIPES: len(pipes)})

            asyncio.run(
                dry_run_pipes(
                    pipes=pipes,
                    allow_signatures=allow_signatures,
                    raise_on_failure=True,
                )
            )
            signature_count = sum(1 for pipe in pipes if pipe.is_signature)
            typer.echo(f"Setup sequence passed OK, config and pipelines are validated.{_format_signatures_summary_suffix(signature_count)}")
    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.VALIDATION)
    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.VALIDATION)


async def _validate_pipe_or_bundle(
    pipe_code: str | None = None,
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
        get_telemetry_manager().track_event(EventName.PIPE_DRY_RUN, properties={EventProperty.PIPE_TYPE: pipe.type})
        try:
            await dry_run_pipe(
                pipe,
                allow_signatures=allow_signatures,
                raise_on_failure=True,
            )
        except SignaturesNotAllowedError as sig_error:
            handle_signatures_not_allowed_error(sig_error, context=ErrorContext.VALIDATION)
        signature_count = len(pipe.collect_signature_refs(pipe_lookup=get_optional_pipe))
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
    bundle_path: Path | None,
    library_dirs: list[Path] | None,
    telemetry_command_label: str = COMMAND,
    allow_signatures: bool = False,
) -> None:
    """Synchronous entry point wrapping the async validation with Pipelex setup/teardown."""
    make_pipelex_for_cli(context=ErrorContext.VALIDATION, needs_inference=False, needs_model_specs=True)

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
