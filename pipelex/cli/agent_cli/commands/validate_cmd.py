"""Agent CLI validate command - simplified pipeline validation with JSON output."""

import asyncio
from pathlib import Path
from typing import Annotated, Any

import typer

from pipelex.base_exceptions import PipelexError
from pipelex.cli.agent_cli.commands.agent_cli_factory import make_pipelex_for_agent_cli
from pipelex.cli.agent_cli.commands.agent_output import agent_error, agent_success, extract_validation_errors
from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import MthdsDecodeError, PipelexInterpreterError
from pipelex.core.interpreter.helpers import is_pipelex_file
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.core.pipes.exceptions import PipeOperatorModelChoiceError
from pipelex.graph.graph_rendering import GraphFormat, render_graph_from_spec
from pipelex.hub import (
    get_library_manager,
    get_required_pipe,
    resolve_library_dirs,
    set_current_library,
)
from pipelex.libraries.pipe.exceptions import PipeNotFoundError
from pipelex.pipe_operators.exceptions import PipeOperatorModelAvailabilityError
from pipelex.pipe_run.dry_run import dry_run_pipe, dry_run_pipes
from pipelex.pipe_run.pipe_run_mode import PipeRunMode
from pipelex.pipelex import Pipelex
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.runner import PipelexRunner
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.tools.misc.chart_utils import FlowchartDirection


async def _validate_all_core(
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate all pipes in all libraries.

    Args:
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    library_manager = get_library_manager()
    library_id, library = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    pipes = library.pipe_library.get_pipes()
    for the_pipe in pipes:
        the_pipe.validate_with_libraries()

    await dry_run_pipes(pipes=pipes, raise_on_failure=True)

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in pipes]

    return {
        "success": True,
        "validated_pipes": validated_pipes,
        "total_pipes": len(pipes),
    }


async def _validate_bundle_core(
    bundle_path: Path,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a bundle file.

    Args:
        bundle_path: Path to the bundle file.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    result = await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    validated_pipes = [{"pipe_code": the_pipe.code, "status": "SUCCESS"} for the_pipe in result.pipes]

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": validated_pipes,
        "total_pipes": len(result.pipes),
    }


async def _validate_pipe_core(
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe.

    Args:
        pipe_code: The pipe code to validate.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    set_current_library(library_id=library_id)
    effective_dirs, _ = resolve_library_dirs(library_dirs)

    if effective_dirs:
        library_manager.load_libraries(library_id=library_id, library_dirs=effective_dirs)

    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, raise_on_failure=True)

    return {
        "success": True,
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


async def _validate_pipe_in_bundle_core(
    bundle_path: Path,
    pipe_code: str,
    library_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Validate a single pipe within a bundle.

    This first validates the bundle to load its pipes into the library,
    then validates only the specified pipe.

    Args:
        bundle_path: Path to the bundle file.
        pipe_code: The pipe code to validate within the bundle.
        library_dirs: List of library directories to search for pipe definitions.

    Returns:
        Dictionary with validation results suitable for JSON serialization.

    Raises:
        ValidateBundleError: If validation fails.
    """
    # Validate the bundle to load all its pipes into the library
    # This ensures all dependencies are available
    await validate_bundle(mthds_file_path=bundle_path, library_dirs=library_dirs)

    # Now get the specific pipe and dry-run only that one
    the_pipe = get_required_pipe(pipe_code=pipe_code)
    await dry_run_pipe(the_pipe, raise_on_failure=True)

    return {
        "success": True,
        "bundle_path": str(bundle_path),
        "validated_pipes": [{"pipe_code": pipe_code, "status": "SUCCESS"}],
        "total_pipes": 1,
    }


async def _generate_graph_for_bundle(
    bundle_path: Path,
    graph_format: GraphFormat,
    library_dirs: list[str] | None = None,
    direction: FlowchartDirection | None = None,
) -> dict[str, Any]:
    """Generate graph visualization for a validated bundle.

    Performs a dry-run pipeline execution with graph tracing enabled,
    then renders and saves graph HTML files alongside the bundle.

    Args:
        bundle_path: Path to the bundle file.
        graph_format: Which graph format(s) to generate.
        library_dirs: Optional library directories for pipe resolution.
        direction: Flowchart layout direction (default: None, uses TB).

    Returns:
        Dictionary with graph_files and graph_output_dir.

    Raises:
        PipelexInterpreterError: If bundle parsing fails.
        PipelineExecutionError: If dry-run execution fails.
    """
    mthds_content = bundle_path.read_text(encoding="utf-8")
    bundle_blueprint = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
    main_pipe_code = bundle_blueprint.main_pipe
    if not main_pipe_code:
        msg = f"Bundle '{bundle_path}' does not declare a main_pipe, cannot generate graph"
        raise PipelexInterpreterError(msg)
    pipe_code: str = main_pipe_code

    execution_config = get_config().pipelex.pipeline_execution_config.with_graph_config_overrides(
        generate_graph=True,
        mock_inputs=True,
    )

    # Ensure the bundle's parent directory is included in library_dirs
    # so PipelexRunner can resolve sibling dependencies
    bundle_parent_dir = str(bundle_path.parent.resolve())
    effective_library_dirs: list[str]
    if library_dirs:
        effective_library_dirs = list(library_dirs)
        if bundle_parent_dir not in effective_library_dirs:
            effective_library_dirs.append(bundle_parent_dir)
    else:
        effective_library_dirs = [bundle_parent_dir]

    runner = PipelexRunner(
        bundle_uri=str(bundle_path),
        pipe_run_mode=PipeRunMode.DRY,
        execution_config=execution_config,
        library_dirs=effective_library_dirs,
    )
    response = await runner.execute_pipeline(
        pipe_code=pipe_code,
        mthds_content=mthds_content,
    )
    pipe_output = response.pipe_output

    if not pipe_output.graph_spec:
        msg = "Pipeline execution did not produce a graph spec"
        raise PipelexError(msg)

    graph_spec = pipe_output.graph_spec

    include_mermaidflow: bool
    include_reactflow: bool
    match graph_format:
        case GraphFormat.MERMAIDFLOW:
            include_mermaidflow = True
            include_reactflow = False
        case GraphFormat.REACTFLOW:
            include_mermaidflow = False
            include_reactflow = True
        case GraphFormat.BOTH:
            include_mermaidflow = True
            include_reactflow = True

    output_dir = bundle_path.parent
    saved_files = await render_graph_from_spec(
        graph_spec=graph_spec,
        graph_config=execution_config.graph_config,
        include_mermaidflow=include_mermaidflow,
        include_reactflow=include_reactflow,
        output_dir=output_dir,
        pipe_code=pipe_code,
        direction=direction,
    )

    return {
        "graph_files": {key: str(path) for key, path in saved_files.items()},
        "graph_output_dir": str(output_dir),
        "direction": str(direction) if direction else None,
    }


def validate_cmd(
    ctx: typer.Context,
    target: Annotated[
        str | None,
        typer.Argument(help="Pipe code or bundle file path (auto-detected)"),
    ] = None,
    pipe: Annotated[
        str | None,
        typer.Option("--pipe", help="Pipe code to validate"),
    ] = None,
    bundle: Annotated[
        str | None,
        typer.Option("--bundle", help="Bundle file path (.mthds)"),
    ] = None,
    validate_all: Annotated[
        bool,
        typer.Option("--all", "-a", help="Validate all pipes in all libraries"),
    ] = False,
    graph: Annotated[
        bool,
        typer.Option("--graph", "-g", help="On successful bundle validation, save graph HTML files and include their paths in the JSON output"),
    ] = False,
    graph_format: Annotated[
        GraphFormat,
        typer.Option("--format", "-f", help="Graph format to generate: mermaidflow, reactflow, or both"),
    ] = GraphFormat.REACTFLOW,
    direction: Annotated[
        FlowchartDirection | None,
        typer.Option("--direction", help="Flowchart direction"),
    ] = None,
    library_dir: Annotated[
        list[str] | None,
        typer.Option("--library-dir", "-L", help="Directory to search for pipe definitions (.mthds files)"),
    ] = None,
) -> None:
    """Validate a pipe, bundle, or all pipes and output JSON results.

    Outputs JSON to stdout on success, JSON to stderr on error with exit code 1.

    Examples:
        pipelex-agent validate my_pipe
        pipelex-agent validate my_bundle.mthds
        pipelex-agent validate my_bundle.mthds --graph
        pipelex-agent validate my_bundle.mthds --graph --format both
        pipelex-agent validate my_bundle.mthds --graph --direction left_to_right
        pipelex-agent validate --all -L ./my_pipes
    """
    library_dirs = [Path(lib_dir) for lib_dir in library_dir] if library_dir else None
    # Handle --all flag
    if validate_all:
        if graph:
            agent_error("--graph requires a bundle target; it cannot be used with --all", "ArgumentError")
        if target or pipe or bundle:
            agent_error("--all cannot be used with a target, --pipe, or --bundle", "ArgumentError")

        make_pipelex_for_agent_cli(library_dirs=library_dirs, log_level=ctx.obj["log_level"])

        try:
            result = asyncio.run(_validate_all_core(library_dirs=library_dirs))
            agent_success(result)

        except ValidateBundleError as exc:
            validation_errors = extract_validation_errors(exc)
            validate_all_extra: dict[str, Any] = {"validation_errors": validation_errors}
            if exc.dry_run_error_message:
                validate_all_extra["dry_run_error"] = exc.dry_run_error_message
            agent_error(exc.message, "ValidateBundleError", cause=exc, **validate_all_extra)

        except PipeOperatorModelChoiceError as exc:
            agent_error(
                exc.message,
                "PipeOperatorModelChoiceError",
                cause=exc,
                pipe_code=exc.pipe_code,
                model_type=str(exc.model_type),
                model_choice=str(exc.model_choice),
            )

        except PipeOperatorModelAvailabilityError as exc:
            agent_error(
                str(exc),
                "PipeOperatorModelAvailabilityError",
                cause=exc,
                pipe_code=exc.pipe_code,
                model_handle=exc.model_handle,
            )

        except Exception as exc:
            agent_error(str(exc), type(exc).__name__, cause=exc)

        finally:
            Pipelex.teardown_if_needed()
        return

    # Validate mutual exclusivity
    provided_options = sum([target is not None, pipe is not None, bundle is not None])
    if provided_options == 0:
        agent_error("No pipe code or bundle file specified. Use --all to validate all pipes.", "ArgumentError")

    # Determine pipe_code and bundle_path from arguments
    pipe_code: str | None = None
    bundle_path: Path | None = None

    if target:
        target_path = Path(target)
        if is_pipelex_file(target_path):
            bundle_path = target_path
            if bundle:
                agent_error("Cannot use --bundle if already passing a bundle file as positional argument", "ArgumentError")
        else:
            pipe_code = target
            if pipe:
                agent_error("Cannot use --pipe if already passing a pipe code as positional argument", "ArgumentError")

    if bundle:
        bundle_path = Path(bundle)

    if pipe:
        pipe_code = pipe

    if not pipe_code and not bundle_path:
        agent_error("No pipe code or bundle file specified", "ArgumentError")

    # --graph requires a bundle
    if graph and not bundle_path:
        agent_error("--graph requires a bundle target; it cannot be used with a standalone pipe", "ArgumentError")

    # Convert library_dirs to list[str] for graph helper (PipelexRunner expects list[str])
    library_dir_strings = [str(lib_dir) for lib_dir in library_dirs] if library_dirs else None

    make_pipelex_for_agent_cli(log_level=ctx.obj["log_level"])

    try:
        if bundle_path and pipe_code:
            # Validate a specific pipe within a bundle
            result = asyncio.run(_validate_pipe_in_bundle_core(bundle_path=bundle_path, pipe_code=pipe_code, library_dirs=library_dirs))
        elif bundle_path:
            # Validate the entire bundle
            result = asyncio.run(_validate_bundle_core(bundle_path=bundle_path, library_dirs=library_dirs))
        else:
            # Validate a standalone pipe
            result = asyncio.run(_validate_pipe_core(pipe_code=pipe_code, library_dirs=library_dirs))  # type: ignore[arg-type]

        # Generate graph if requested and validation succeeded with a bundle
        if graph and bundle_path:
            try:
                graph_result = asyncio.run(
                    _generate_graph_for_bundle(
                        bundle_path=bundle_path,
                        graph_format=graph_format,
                        library_dirs=library_dir_strings,
                        direction=direction,
                    )
                )
                result.update(graph_result)
            except PipelineExecutionError as exc:
                graph_extra: dict[str, Any] = {
                    "pipe_code": exc.pipe_code,
                    "pipe_stack": exc.pipe_stack,
                }
                if exc.__cause__:
                    graph_extra["cause_type"] = type(exc.__cause__).__name__
                    graph_extra["cause_message"] = str(exc.__cause__)
                agent_error(f"Graph generation failed: {exc.message}", "PipelineExecutionError", cause=exc, **graph_extra)
            except (PipelexInterpreterError, MthdsDecodeError) as exc:
                agent_error(f"Graph generation failed: {exc}", type(exc).__name__, cause=exc)
            except typer.Exit:
                raise
            except Exception as exc:
                agent_error(f"Graph generation failed: {exc}", type(exc).__name__, cause=exc)

        agent_success(result)

    except PipeNotFoundError as exc:
        error_message = str(exc)
        if pipe_code == "all":
            error_message += " Did you mean '--all'?"
        agent_error(error_message, "PipeNotFoundError", cause=exc)

    except FileNotFoundError as exc:
        agent_error(f"Bundle file not found: {bundle_path}", "FileNotFoundError", cause=exc)

    except ValidateBundleError as exc:
        validation_errors = extract_validation_errors(exc)
        extra: dict[str, Any] = {"validation_errors": validation_errors}
        if exc.dry_run_error_message:
            extra["dry_run_error"] = exc.dry_run_error_message
        agent_error(exc.message, "ValidateBundleError", cause=exc, **extra)

    except PipeOperatorModelChoiceError as exc:
        agent_error(
            exc.message,
            "PipeOperatorModelChoiceError",
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
        agent_error(exc.message, "PipeOperatorModelAvailabilityError", cause=exc, **availability_extra)

    except Exception as exc:
        agent_error(str(exc), type(exc).__name__, cause=exc)

    finally:
        Pipelex.teardown_if_needed()
