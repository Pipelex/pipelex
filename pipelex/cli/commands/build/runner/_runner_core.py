from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import typer
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from posthog import tag

from pipelex.builder.runner_code import generate_runner_code
from pipelex.cli.cli_factory import make_pipelex_for_cli
from pipelex.cli.error_handlers import (
    ErrorContext,
    handle_model_availability_error,
    handle_model_choice_error,
)
from pipelex.codegen.emission import write_stamped_projection
from pipelex.codegen.emitters.naming import runtime_to_emitted_class_names
from pipelex.codegen.emitters.target import CodegenKind, CodegenTarget
from pipelex.codegen.emitters.types_emitter import emit_types
from pipelex.codegen.resolved_concepts import resolve_concepts_from_crate
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.core.pipes.inputs.exceptions import PipeInputError
from pipelex.core.pipes.variable_multiplicity import parse_concept_with_multiplicity
from pipelex.hub import (
    get_current_library_id_or_none,
    get_library_manager,
    get_required_pipe,
    get_telemetry_manager,
)
from pipelex.libraries.crate_normalization import normalize_crate
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipelex import PACKAGE_VERSION
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.system.runtime import IntegrationMode
from pipelex.system.telemetry.events import EventProperty
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    save_text_to_path,
)

if TYPE_CHECKING:
    from pathlib import Path

    from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint

COMMAND = "build"
SUB_COMMAND_RUNNER = "runner"


async def _prepare_runner_core(
    *, pipe_code: str | None = None, bundle_path: Path | None = None, output_path: Path | None = None, library_dirs: list[Path] | None = None
) -> None:
    """Core logic for generating a Python runner file."""
    all_blueprints: list[PipelexBundleBlueprint] = []

    if bundle_path:
        try:
            validate_bundle_result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)
            all_blueprints.extend(validate_bundle_result.blueprints)
            first_blueprint = validate_bundle_result.blueprints[0]
            if not pipe_code:
                main_pipe_code = first_blueprint.main_pipe
                if not main_pipe_code:
                    typer.secho(
                        f"Bundle '{bundle_path}' has no main_pipe declared. Use --pipe to specify which pipe to use.",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    raise typer.Exit(1)
                typer.echo(f"Using main pipe '{main_pipe_code}' from bundle '{bundle_path}'")
                pipe_code = main_pipe_code
            else:
                typer.echo(f"Using pipe '{pipe_code}' from bundle '{bundle_path}'")
        except FileNotFoundError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except ValidateBundleError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
        except PipeInputError as exc:
            typer.secho(f"Failed to load bundle '{bundle_path}': {exc}", fg=typer.colors.RED, err=True)
            raise typer.Exit(1) from exc
    else:
        typer.secho("Failed to run: no bundle file specified", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)

    try:
        the_pipe = get_required_pipe(pipe_code=pipe_code)
    except Exception as exc:
        # CLI command boundary: any failure resolving the pipe is reported to the user and exits via typer.Exit.
        typer.secho(f"Error: Could not find pipe '{pipe_code}': {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    if output_path:
        final_output_path = output_path
    else:
        bundle_dir = bundle_path.parent
        final_output_path = bundle_dir / f"run_{pipe_code}.py"
    output_dir = final_output_path.parent

    # Emit the types projection (stamped structures.py + codegen.lock) into structures/ via the
    # codegen engine. validate_bundle left its loaded-and-validated library open and current, so the
    # crate is read from there (D6: the normalized crate is built from a valid library).
    structures_output_dir = output_dir / "structures"
    class_name_overrides: dict[str, str] = {}
    library_id = get_current_library_id_or_none()
    crate = get_library_manager().get_crate(library_id) if library_id else None
    if crate is not None:
        normalized_crate = normalize_crate(crate, mthds_version=MTHDS_STANDARD_VERSION)
        emitted = emit_types(normalized_crate, target=CodegenTarget.PYTHON_STRUCTURES)
        report = write_stamped_projection(
            emitted,
            output_dir=structures_output_dir,
            crate_fingerprint=normalized_crate.fingerprint,
            engine_version=PACKAGE_VERSION,
            kind=CodegenKind.TYPES,
            target=CodegenTarget.PYTHON_STRUCTURES,
        )
        for filename in report.written:
            typer.secho(f"Generated {structures_output_dir / filename}", fg=typer.colors.GREEN)
        for filename in report.unchanged:
            typer.secho(f"Unchanged {structures_output_dir / filename}", fg=typer.colors.BLUE)
        for filename in report.removed:
            typer.secho(f"Removed stale {structures_output_dir / filename}", fg=typer.colors.YELLOW)
        class_name_overrides = runtime_to_emitted_class_names(resolve_concepts_from_crate(normalized_crate))

    output_is_list = False
    for blueprint in all_blueprints:
        if blueprint.pipe and pipe_code in blueprint.pipe:
            pipe_blueprint = blueprint.pipe[pipe_code]
            output_parse = parse_concept_with_multiplicity(pipe_blueprint.output)
            output_is_list = output_parse.multiplicity is not None
            break

    if library_dirs:
        pipelex_library_dir = str(library_dirs[0].resolve())
    else:
        pipelex_library_dir = str(bundle_path.parent.resolve())

    try:
        runner_code = generate_runner_code(
            pipe=the_pipe,
            output_multiplicity=output_is_list,
            library_dir=pipelex_library_dir,
            class_name_overrides=class_name_overrides,
        )
    except Exception as exc:
        # CLI command boundary: any failure generating the runner code is reported to the user and exits via typer.Exit.
        typer.secho(f"Error generating runner code: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc

    try:
        ensure_directory_for_file_path(file_path=final_output_path)
        save_text_to_path(text=runner_code, path=final_output_path)
        typer.secho(f"Generated runner file: {final_output_path}", fg=typer.colors.GREEN)
    except Exception as exc:
        # CLI command boundary: any failure writing the file is reported to the user and exits via typer.Exit.
        typer.secho(f"Error saving file: {exc}", fg=typer.colors.RED)
        raise typer.Exit(1) from exc


def execute_prepare_runner(
    *,
    pipe_code: str | None,
    bundle_path: Path | None,
    output_path: Path | None,
    library_dirs: list[Path] | None = None,
    telemetry_command_label: str = f"{COMMAND} {SUB_COMMAND_RUNNER}",
) -> None:
    """Synchronous entry point wrapping the async runner generation with Pipelex setup/teardown."""
    pipelex_instance = make_pipelex_for_cli(context=ErrorContext.VALIDATION_BEFORE_BUILD_RUNNER)

    try:
        with get_telemetry_manager().telemetry_context():
            tag(name=EventProperty.INTEGRATION, value=IntegrationMode.CLI)
            tag(name=EventProperty.PIPELEX_VERSION, value=PACKAGE_VERSION)
            tag(name=EventProperty.CLI_COMMAND, value=telemetry_command_label)

            asyncio.run(
                _prepare_runner_core(
                    pipe_code=pipe_code,
                    bundle_path=bundle_path,
                    output_path=output_path,
                    library_dirs=library_dirs,
                )
            )

    except PipeOperatorModelChoiceError as exc:
        handle_model_choice_error(exc, context=ErrorContext.BUILD)

    except PipeOperatorModelAvailabilityError as exc:
        handle_model_availability_error(exc, context=ErrorContext.BUILD)

    finally:
        pipelex_instance.teardown()
