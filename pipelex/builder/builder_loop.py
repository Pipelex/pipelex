from pathlib import Path

from pipelex import log, pretty_print
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.builder_validation import fix_inputs_consistency
from pipelex.client.protocol import PipelineInputs
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintFixableErrorType
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.hub import get_console, get_required_pipe
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipeline.exceptions import PipelineExecutionError
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.tools.misc.file_utils import get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


class BuilderLoop:
    async def build_and_fix(
        self,
        pipe_code: str,
        inputs: PipelineInputs | None = None,
        is_save_first_iteration_enabled: bool = True,
        is_save_second_iteration_enabled: bool = True,
        is_save_working_memory_enabled: bool = True,
    ) -> PipelexBundleSpec:
        pretty_print(f"Building and fixing with {pipe_code}")
        try:
            pipe_output = await execute_pipeline(
                pipe_code=pipe_code,
                library_path=str(Path(__file__).parent),
                inputs=inputs,
            )
        except PipelineExecutionError as exc:
            msg = f"Builder loop: Failed to execute pipeline: {exc}."
            console = get_console()
            console.print_exception()
            raise PipeBuilderError(message=msg) from exc

        if is_save_working_memory_enabled:
            working_memory_path = get_incremental_file_path(
                base_path="results",
                base_name="working_memory",
                extension="json",
            )
            save_as_json_to_path(object_to_save=pipe_output.working_memory.smart_dump(), path=working_memory_path)

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())

        if is_save_first_iteration_enabled:
            first_iteration_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_1st_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=first_iteration_path)

        # Fix input consistency for all PipeController pipes before validation
        log.dev("🔄 Calling fix_inputs_consistency() to ensure PipeController inputs are consistent")
        pipelex_bundle_spec = await fix_inputs_consistency(bundle_spec=pipelex_bundle_spec)

        # Save the fixed bundle for debugging if enabled
        if is_save_first_iteration_enabled:
            plx_content_after_fix = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
            first_iteration_after_fix_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_1st_iteration_after_fix",
                extension="plx",
            )
            save_text_to_path(text=plx_content_after_fix, path=first_iteration_after_fix_path)

        bundle_blueprint = pipelex_bundle_spec.to_blueprint()
        try:
            await validate_bundle(blueprints=[bundle_blueprint])
        except ValidateBundleError as exc:
            self._fix_bundle_validaiton_error(
                bundle_error=exc, pipelex_bundle_spec=pipelex_bundle_spec, is_save_second_iteration_enabled=is_save_second_iteration_enabled
            )

        return pipelex_bundle_spec

    def _fix_bundle_validaiton_error(
        self,
        bundle_error: ValidateBundleError,
        pipelex_bundle_spec: PipelexBundleSpec,
        is_save_second_iteration_enabled: bool,
    ) -> PipelexBundleSpec:
        """Fix validation errors in the bundle spec.

        Currently supports fixing:
        - PIPE_MISSING_INPUT_VARIABLE / PIPE_EXTRANEOUS_INPUT_VARIABLE
        - PIPE_SEQUENCE_OUTPUT_MISMATCH
        """
        fixed_pipes: list[PipeSpecUnion] = []

        # Process categorized validation errors
        for val_error in bundle_error.validation_errors:
            if not val_error.pipe_code or not pipelex_bundle_spec.pipe:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(val_error.pipe_code)
            if not pipe_spec:
                continue

            match val_error.error_type:
                case (
                    PipelexBundleBlueprintFixableErrorType.PIPE_MISSING_INPUT_VARIABLE
                    | PipelexBundleBlueprintFixableErrorType.PIPE_EXTRANEOUS_INPUT_VARIABLE
                ):
                    # Fix input variables for PipeController
                    if not AllowedPipeCategories.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()
                    new_inputs: dict[str, str] = {}
                    for named_requirement in needed_inputs.named_input_requirements:
                        new_inputs[named_requirement.variable_name] = named_requirement.concept.code
                    pipe_spec.inputs = new_inputs
                    fixed_pipes.append(pipe_spec)
                    log.dev(f"Fixed inputs for '{val_error.pipe_code}': {new_inputs}")

                case PipelexBundleBlueprintFixableErrorType.PIPE_SEQUENCE_OUTPUT_MISMATCH:
                    # Fix pipe sequence output to match last step output
                    if val_error.last_step_output_concept:
                        pipe_spec.output = val_error.last_step_output_concept
                        fixed_pipes.append(pipe_spec)
                        log.dev(f"Fixed PipeSequence '{val_error.pipe_code}' output to '{val_error.last_step_output_concept}'")
                case PipelexBundleBlueprintFixableErrorType.PIPE_SEQUENCE_EMPTY_STEPS:
                    continue
                case PipelexBundleBlueprintFixableErrorType.PIPE_INADEQUATE_INPUT_CONCEPT:
                    continue
                case PipelexBundleBlueprintFixableErrorType.PIPE_TOO_MANY_CANDIDATE_INPUTS:
                    continue
                case PipelexBundleBlueprintFixableErrorType.PIPE_INADEQUATE_OUTPUT_CONCEPT:
                    continue
                case PipelexBundleBlueprintFixableErrorType.DOMAIN_CODE_INVALID:
                    continue
                case PipelexBundleBlueprintFixableErrorType.MAIN_PIPE_NOT_FOUND:
                    continue
                case PipelexBundleBlueprintFixableErrorType.MISSING_REQUIRED_FIELD:
                    continue
                case PipelexBundleBlueprintFixableErrorType.TYPE_MISMATCH:
                    continue
                case PipelexBundleBlueprintFixableErrorType.EXTRA_FORBIDDEN_FIELD:
                    continue
                case PipelexBundleBlueprintFixableErrorType.DISCRIMINATOR_MISSING:
                    continue
                case PipelexBundleBlueprintFixableErrorType.ENUM_INVALID_VALUE:
                    continue
                case PipelexBundleBlueprintFixableErrorType.UNKNOWN:
                    continue
                case _:
                    continue

        # Save fixed bundle if we made changes
        if fixed_pipes and is_save_second_iteration_enabled:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)
            pretty_print(pipelex_bundle_spec, title="Pipelex Bundle Spec • 2nd iteration")
            plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
            second_iteration_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_2nd_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=second_iteration_path)

        return pipelex_bundle_spec
