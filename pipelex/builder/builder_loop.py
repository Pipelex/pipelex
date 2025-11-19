from pathlib import Path

from pipelex import log, pretty_print
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.client.protocol import PipelineInputs
from pipelex.core.bundles.exceptions import PipelexBundleBlueprintFixableErrorType, PipeValidationErrorType
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

        bundle_blueprint = pipelex_bundle_spec.to_blueprint()
        try:
            await validate_bundle(blueprints=[bundle_blueprint])
        except ValidateBundleError as exc:
            pipelex_bundle_spec = self._fix_bundle_validation_error(
                bundle_error=exc, pipelex_bundle_spec=pipelex_bundle_spec, is_save_second_iteration_enabled=is_save_second_iteration_enabled
            )

        return pipelex_bundle_spec

    def _fix_bundle_validation_error(
        self,
        bundle_error: ValidateBundleError,
        pipelex_bundle_spec: PipelexBundleSpec,
        is_save_second_iteration_enabled: bool,
    ) -> PipelexBundleSpec:
        """Fix validation errors in the bundle spec.

        Currently supports fixing:
        - MISSING_INPUT_VARIABLE / EXTRANEOUS_INPUT_VARIABLE / INPUT_REQUIREMENT_MISMATCH (for PipeController only)
        - PIPE_SEQUENCE_OUTPUT_MISMATCH
        """
        fixed_pipes: list[PipeSpecUnion] = []

        # Process pipe validation error data (MISSING_INPUT_VARIABLE / EXTRANEOUS_INPUT_VARIABLE for PipeController)
        for val_error in bundle_error.pipe_validation_error_data:
            if not val_error.pipe_code or not pipelex_bundle_spec.pipe:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(val_error.pipe_code)
            if not pipe_spec:
                continue

            match val_error.error_type:
                case PipeValidationErrorType.INPUT_REQUIREMENT_MISMATCH:
                    # Fix input requirement mismatch by updating the specific mismatched input(s)
                    # This applies to ALL pipe categories
                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()

                    # Start with existing inputs, we'll only override the mismatched ones
                    new_inputs: dict[str, str] = dict(pipe_spec.inputs) if pipe_spec.inputs else {}

                    # Get the variable names that have mismatches
                    mismatched_variables = val_error.variable_names or []

                    # Update only the mismatched inputs with the correct concept from needed_inputs
                    for variable_name in mismatched_variables:
                        for named_requirement in needed_inputs.named_input_requirements:
                            if named_requirement.variable_name == variable_name:
                                concept_code = named_requirement.concept.code
                                # Preserve multiplicity brackets
                                if named_requirement.multiplicity is not None:
                                    if named_requirement.multiplicity is True:
                                        # Variable-length list []
                                        concept_code = f"{concept_code}[]"
                                    else:
                                        # Fixed-length list [N] where N is an int
                                        concept_code = f"{concept_code}[{named_requirement.multiplicity}]"
                                new_inputs[variable_name] = concept_code
                                log.dev(f"Fixed input '{variable_name}' for '{val_error.pipe_code}': {concept_code}")
                                break

                    pipe_spec.inputs = new_inputs
                    fixed_pipes.append(pipe_spec)

                case PipeValidationErrorType.MISSING_INPUT_VARIABLE | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE:
                    # Fix input variables for PipeController ONLY by copying all requirements from needed_inputs
                    if not AllowedPipeCategories.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()
                    fixed_inputs: dict[str, str] = {}
                    for named_requirement in needed_inputs.named_input_requirements:
                        concept_code = named_requirement.concept.code
                        # Preserve multiplicity brackets
                        if named_requirement.multiplicity is not None:
                            if named_requirement.multiplicity is True:
                                # Variable-length list []
                                concept_code = f"{concept_code}[]"
                            else:
                                # Fixed-length list [N] where N is an int
                                concept_code = f"{concept_code}[{named_requirement.multiplicity}]"
                        fixed_inputs[named_requirement.variable_name] = concept_code
                    pipe_spec.inputs = fixed_inputs
                    fixed_pipes.append(pipe_spec)
                    log.dev(f"Fixed inputs for '{val_error.pipe_code}': {fixed_inputs}")

                case _:
                    # Other error types not handled for pipe validation errors
                    continue

        # Process pipelex bundle blueprint validation errors (PIPE_SEQUENCE_OUTPUT_MISMATCH)
        for blueprint_error in bundle_error.pipelex_bundle_blueprint_validation_errors:
            if blueprint_error.error_type != PipelexBundleBlueprintFixableErrorType.PIPE_SEQUENCE_OUTPUT_MISMATCH:
                continue

            if not blueprint_error.pipe_code or not pipelex_bundle_spec.pipe:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(blueprint_error.pipe_code)
            if not pipe_spec or not isinstance(pipe_spec, PipeSequenceSpec):
                continue

            # Get the last step's output
            if not pipe_spec.steps:
                continue

            last_step = pipe_spec.steps[-1]
            last_step_pipe_code = last_step.pipe_code

            # Get the last step's pipe spec to retrieve its output
            last_step_pipe_spec = pipelex_bundle_spec.pipe.get(last_step_pipe_code)
            if not last_step_pipe_spec:
                continue

            # Set the sequence output to match the last step's output
            pipe_spec.output = last_step_pipe_spec.output
            fixed_pipes.append(pipe_spec)
            log.dev(f"Fixed output for '{blueprint_error.pipe_code}': set to '{last_step_pipe_spec.output}' (from last step '{last_step_pipe_code}')")

        # Reconstruct bundle if we made changes
        if fixed_pipes:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)
            if is_save_second_iteration_enabled:
                pretty_print(pipelex_bundle_spec, title="Pipelex Bundle Spec • 2nd iteration")
                plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
                second_iteration_path = get_incremental_file_path(
                    base_path="results",
                    base_name="generated_pipeline_2nd_iteration",
                    extension="plx",
                )
                save_text_to_path(text=plx_content, path=second_iteration_path)

        return pipelex_bundle_spec
