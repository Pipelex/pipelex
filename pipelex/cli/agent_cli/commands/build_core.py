"""Core build logic for agent CLI."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from pipelex import log
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.builder_loop import BuilderLoop, maybe_generate_manifest_for_output
from pipelex.builder.conventions import DEFAULT_INPUTS_FILE_NAME
from pipelex.builder.exceptions import PipelexBundleSpecBlueprintError
from pipelex.config import get_config
from pipelex.core.interpreter.helpers import MTHDS_EXTENSION
from pipelex.hub import get_required_pipe
from pipelex.language.mthds_factory import MthdsFactory
from pipelex.pipeline.exceptions import PipeExecutionError
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.tools.misc.file_utils import (
    ensure_directory_for_file_path,
    get_incremental_directory_path,
    get_incremental_file_path,
    save_text_to_path,
)
from pipelex.tools.misc.json_utils import save_as_json_to_path


class BuildPipeResult(BaseModel):
    """Result of building a pipe, containing output paths and metadata."""

    output_dir: Path
    mthds_file: Path
    inputs_file: Path | None = None
    main_pipe_code: str
    domain: str
    pipe_inputs: dict[str, str] | None = None
    pipe_output: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    def to_agent_json(self) -> dict[str, Any]:
        """Return dict for JSON output to agent.

        Returns:
            Dictionary with string paths suitable for JSON serialization.
        """
        result: dict[str, Any] = {
            "output_dir": str(self.output_dir),
            "mthds_file": str(self.mthds_file),
            "main_pipe_code": self.main_pipe_code,
            "domain": self.domain,
        }
        if self.inputs_file:
            result["inputs_file"] = str(self.inputs_file)
        if self.pipe_inputs is not None:
            result["pipe_inputs"] = self.pipe_inputs
        if self.pipe_output is not None:
            result["pipe_output"] = self.pipe_output
        return result


class BuildPipeError(Exception):
    """Error during pipe building."""

    def __init__(self, message: str, failure_memory_path: Path | None = None):
        super().__init__(message)
        self.message = message
        self.failure_memory_path = failure_memory_path


async def build_pipe_core(
    prompt: str,
    builder_pipe: str = "pipe_builder",
    output_dir: str | None = None,
    output_name: str | None = None,
    generate_inputs: bool = True,
    execution_config: PipelineExecutionConfig | None = None,
) -> BuildPipeResult:
    """Core pipe building logic for agent CLI.

    Args:
        prompt: The prompt describing what the pipeline should do.
        builder_pipe: The builder pipe to use for generating the pipeline.
        output_dir: Directory where files will be generated.
        output_name: Base name for the generated directory (without extension).
        generate_inputs: Whether to generate inputs.json file.
        execution_config: Configuration for pipeline execution.

    Returns:
        BuildPipeResult with output paths and metadata.

    Raises:
        BuildPipeError: If the build fails.
    """
    builder_config = get_config().pipelex.builder_config

    if execution_config is None:
        execution_config = get_config().pipelex.pipeline_execution_config

    # Build the pipeline
    builder_loop = BuilderLoop()
    try:
        pipelex_bundle_spec, _ = await builder_loop.build_and_fix(
            builder_pipe=builder_pipe,
            inputs={"brief": prompt},
            execution_config=execution_config,
            output_dir=output_dir,
            is_save_first_iteration_enabled=False,
            is_save_second_iteration_enabled=False,
            is_save_working_memory_enabled=False,
        )
    except (PipeBuilderError, PipeExecutionError) as exc:
        msg = f"Builder loop: Failed to execute pipeline: {exc}."
        failure_memory_path: Path | None = None

        if isinstance(exc, PipeBuilderError) and exc.working_memory:
            failure_memory_path = get_incremental_file_path(
                base_path=output_dir or builder_config.default_output_dir,
                base_name="failure_memory",
                extension="json",
            )
            save_as_json_to_path(
                object_to_save=exc.working_memory.smart_dump(),
                path=str(failure_memory_path),
            )
            log.error(f"Failure memory saved to: {failure_memory_path}")

        raise BuildPipeError(message=msg, failure_memory_path=failure_memory_path) from exc

    # Determine base output directory
    base_dir = output_dir or builder_config.default_output_dir

    # Determine output path - always generate directory with bundle.mthds
    dir_name = output_name or builder_config.default_directory_base_name
    bundle_file_name = Path(f"{builder_config.default_bundle_file_name}{MTHDS_EXTENSION}")

    extras_output_dir = get_incremental_directory_path(
        base_path=base_dir,
        base_name=dir_name,
    )
    mthds_file_path = Path(extras_output_dir) / bundle_file_name

    # Save the MTHDS file
    ensure_directory_for_file_path(file_path=str(mthds_file_path))
    try:
        mthds_content = MthdsFactory.make_mthds_content(blueprint=pipelex_bundle_spec.to_blueprint())
    except PipelexBundleSpecBlueprintError as exc:
        msg = f"Failed to convert bundle spec to blueprint: {exc}"
        raise BuildPipeError(message=msg) from exc
    save_text_to_path(text=mthds_content, path=str(mthds_file_path))

    # Generate METHODS.toml if multiple domains exist in output dir
    manifest_path = maybe_generate_manifest_for_output(output_dir=Path(extras_output_dir))
    if manifest_path:
        log.verbose(f"Package manifest generated: {manifest_path}")

    main_pipe_code = pipelex_bundle_spec.main_pipe or ""
    domain = pipelex_bundle_spec.domain or ""

    inputs_file_path: Path | None = None
    pipe_inputs: dict[str, str] | None = None
    pipe_output: str | None = None

    # Load pipe metadata (inputs/output) and optionally generate inputs.json
    if main_pipe_code:
        try:
            pipe = get_required_pipe(pipe_code=main_pipe_code)
            pipe_inputs = {name: stuff_spec.to_bundle_representation() for name, stuff_spec in pipe.inputs.items}
            pipe_output = pipe.output.to_bundle_representation()

            if generate_inputs:
                inputs_json_str = pipe.inputs.render_inputs(indent=2)
                inputs_file_path = Path(extras_output_dir) / DEFAULT_INPUTS_FILE_NAME
                save_text_to_path(text=inputs_json_str, path=str(inputs_file_path))
        except Exception as exc:
            log.warning(f"Could not load pipe metadata: {exc}")

    return BuildPipeResult(
        output_dir=Path(extras_output_dir),
        mthds_file=mthds_file_path,
        inputs_file=inputs_file_path,
        main_pipe_code=main_pipe_code,
        domain=domain,
        pipe_inputs=pipe_inputs,
        pipe_output=pipe_output,
    )
