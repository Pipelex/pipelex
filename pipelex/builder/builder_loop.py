from pathlib import Path

from pipelex import builder, log
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.client.protocol import PipelineInputs
from pipelex.config import get_config
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.core.pipes.pipe_blueprint import PipeCategory
from pipelex.core.pipes.variable_multiplicity import format_concept_with_multiplicity
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import get_required_pipe
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.tools.misc.file_utils import get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path


class BuilderLoop:
    async def build_and_fix(
        self,
        builder_pipe: str,
        inputs: PipelineInputs | None = None,
        execution_config: PipelineExecutionConfig | None = None,
        is_save_first_iteration_enabled: bool = True,
        is_save_second_iteration_enabled: bool = True,
        is_save_working_memory_enabled: bool = True,
        output_dir: str | None = None,
    ) -> tuple[PipelexBundleSpec, GraphSpec | None]:
        # TODO: Doesn't make sense to be able to put a builder_pipe code but hardcoding the Path to the builder pipe.
        pipe_output = await execute_pipeline(
            pipe_code=builder_pipe,
            library_dirs=[str(Path(builder.__file__).parent)],
            inputs=inputs,
            execution_config=execution_config,
        )

        if is_save_working_memory_enabled:
            working_memory_path = get_incremental_file_path(
                base_path=output_dir or "results/pipe-builder",
                base_name="working_memory",
                extension="json",
            )
            save_as_json_to_path(object_to_save=pipe_output.working_memory.smart_dump(), path=working_memory_path, create_directory=True)

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
        plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())

        if is_save_first_iteration_enabled:
            first_iteration_path = get_incremental_file_path(
                base_path=output_dir or "results/pipe-builder",
                base_name="generated_pipeline_1st_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=first_iteration_path, create_directory=True)

        bundle_blueprint = pipelex_bundle_spec.to_blueprint()
        max_attempts = get_config().pipelex.builder_config.fix_loop_max_attempts
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt == 1:
                    await validate_bundle(blueprints=[bundle_blueprint])
                else:
                    log.info(f"Validating bundle after fixes (attempt {attempt}/{max_attempts})...")
                    fixed_bundle_blueprint = pipelex_bundle_spec.to_blueprint()
                    await validate_bundle(blueprints=[fixed_bundle_blueprint])

                if attempt > 1:
                    log.info(f"✅ Bundle validation passed after fixes (attempt {attempt}/{max_attempts})")
                break  # Validation passed, exit the loop

            except ValidateBundleError as exc:
                if attempt < max_attempts:
                    log.info(f"⚠️ Validation failed on attempt {attempt}/{max_attempts}, attempting fixes...")
                    pipelex_bundle_spec = self._fix_bundle_validation_error(
                        bundle_error=exc, pipelex_bundle_spec=pipelex_bundle_spec, is_save_second_iteration_enabled=is_save_second_iteration_enabled
                    )
                else:
                    # Final attempt failed, re-raise the error
                    log.error(f"❌ Validation failed after {max_attempts} attempts, raising error")
                    raise

        return pipelex_bundle_spec, pipe_output.graph_spec

    def _fix_bundle_validation_error(
        self,
        bundle_error: ValidateBundleError,
        pipelex_bundle_spec: PipelexBundleSpec,
        is_save_second_iteration_enabled: bool,
    ) -> PipelexBundleSpec:
        fixed_pipes: list[PipeSpecUnion] = []
        added_concepts: list[str] = []
        # TODO: Auto remove the creation of native concept by the pipe builder
        # Handle pipe factory errors (e.g., missing output concepts)
        for factory_error in bundle_error.pipe_factory_errors:
            match factory_error.error_type:
                case PipeFactoryErrorType.UNKNOWN_CONCEPT:
                    # Fix unknown concept by adding a new concept that refines Text to the bundle
                    unknown_concept_code = factory_error.missing_concept_code
                    if not unknown_concept_code:
                        continue

                    # Create a simple concept that refines Text
                    new_concept = ConceptSpec(
                        the_concept_code=unknown_concept_code,
                        description=unknown_concept_code,
                        refines="Text",
                    )

                    # Add the concept to the bundle
                    if pipelex_bundle_spec.concept is None:
                        pipelex_bundle_spec.concept = {}

                    pipelex_bundle_spec.concept[unknown_concept_code] = new_concept
                    added_concepts.append(unknown_concept_code)
                    log.info(f"🔧 Added unknown concept '{unknown_concept_code}' (refines Text) to bundle for pipe '{factory_error.pipe_code}'")

                case PipeFactoryErrorType.UNKNOWN_FACTORY_ERROR:
                    continue

        # Handle pipe validation errors
        for val_error in bundle_error.pipe_validation_error_data:
            if not val_error.pipe_code or not pipelex_bundle_spec.pipe:
                continue

            pipe_spec = pipelex_bundle_spec.pipe.get(val_error.pipe_code)
            if not pipe_spec:
                continue

            match val_error.error_type:
                case PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH:
                    # Fix input stuff spec mismatch by updating the specific mismatched input(s)
                    # This applies to ALL pipe categories (operators and controllers)
                    if not PipeCategory.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()

                    # Start with existing inputs, we'll only override the mismatched ones
                    new_inputs: dict[str, str] = dict(pipe_spec.inputs) if pipe_spec.inputs else {}

                    # Get the variable names that have mismatches
                    mismatched_variables = val_error.variable_names or []

                    # Update only the mismatched inputs with the correct concept from needed_inputs
                    for variable_name in mismatched_variables:
                        for named_stuff_spec in needed_inputs.named_stuff_specs:
                            if named_stuff_spec.variable_name == variable_name:
                                old_value = new_inputs.get(variable_name, "NOT SET")
                                concept_code_with_multiplicity = format_concept_with_multiplicity(
                                    concept_code_or_string=named_stuff_spec.concept.code,
                                    multiplicity=named_stuff_spec.multiplicity,
                                )
                                new_inputs[variable_name] = concept_code_with_multiplicity
                                # TODO: return a structured report of what was done, let the caller decide if they want to print it or act on it
                                log.info(
                                    f"🔧 Fixed input requirement mismatch for pipe '{val_error.pipe_code}': input '{variable_name}' \
                                        changed from '{old_value}' → '{concept_code_with_multiplicity}'"
                                )
                                break

                    pipe_spec.inputs = new_inputs
                    fixed_pipes.append(pipe_spec)

                case PipeValidationErrorType.MISSING_INPUT_VARIABLE | PipeValidationErrorType.EXTRANEOUS_INPUT_VARIABLE:
                    # Fix input variables for PipeController ONLY by copying all requirements from needed_inputs
                    if not PipeCategory.is_controller_by_str(category_str=pipe_spec.pipe_category):
                        continue

                    pipe = get_required_pipe(pipe_code=val_error.pipe_code)
                    needed_inputs = pipe.needed_inputs()
                    old_inputs = dict(pipe_spec.inputs) if pipe_spec.inputs else {}
                    fixed_inputs: dict[str, str] = {}
                    for named_stuff_spec in needed_inputs.named_stuff_specs:
                        concept_code_with_multiplicity = format_concept_with_multiplicity(
                            concept_code_or_string=named_stuff_spec.concept.code,
                            multiplicity=named_stuff_spec.multiplicity,
                        )
                        fixed_inputs[named_stuff_spec.variable_name] = concept_code_with_multiplicity

                    # Only apply fix if it actually changes something (avoid infinite loops)
                    if fixed_inputs != old_inputs:
                        pipe_spec.inputs = fixed_inputs
                        fixed_pipes.append(pipe_spec)
                        log.info(f"🔧 Fixed input variables for pipe '{val_error.pipe_code}': BEFORE={old_inputs} → AFTER={fixed_inputs}")
                    else:
                        log.warning(
                            f"⚠️ Cannot auto-fix MISSING_INPUT_VARIABLE for pipe '{val_error.pipe_code}': needed_inputs() \
                                doesn't include the missing variable '{val_error.variable_names}'. \
                                    This might be an intermediate variable that shouldn't be in inputs."
                        )

                case PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT | PipeValidationErrorType.INADEQUATE_OUTPUT_MULTIPLICITY:
                    # Fix output concept/multiplicity mismatch for PipeSequence by updating to match last step's output
                    if not isinstance(pipe_spec, PipeSequenceSpec):
                        continue

                    last_step = pipe_spec.steps[-1]
                    last_step_pipe_code = last_step.pipe_code

                    # Get the last step's pipe spec to retrieve its output
                    last_step_pipe_spec = pipelex_bundle_spec.pipe.get(last_step_pipe_code)
                    if not last_step_pipe_spec:
                        continue

                    old_output = pipe_spec.output
                    new_output = last_step_pipe_spec.output

                    # Set the sequence output to match the last step's output
                    pipe_spec.output = new_output
                    fixed_pipes.append(pipe_spec)
                    # TODO: return a structured report of what was done, let the caller decide if they want to print it or act on it
                    error_kind = "concept" if val_error.error_type == PipeValidationErrorType.INADEQUATE_OUTPUT_CONCEPT else "multiplicity"
                    log.info(
                        f"🔧 Fixed output {error_kind} for pipe '{val_error.pipe_code}': output changed from '{old_output}' → \
                            '{new_output}' (matching last step '{last_step_pipe_code}')"
                    )

                case (
                    PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                    | PipeValidationErrorType.IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE
                    | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
                    | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                ):
                    continue

        # Reconstruct bundle if we made pipe changes
        if fixed_pipes:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)

        # Save second iteration if we made any changes (pipes or concepts)
        if (fixed_pipes or added_concepts) and is_save_second_iteration_enabled:
            plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
            second_iteration_path = get_incremental_file_path(
                base_path="results",
                base_name="generated_pipeline_2nd_iteration",
                extension="plx",
            )
            save_text_to_path(text=plx_content, path=second_iteration_path)

        return pipelex_bundle_spec
