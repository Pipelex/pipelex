from pathlib import Path
from typing import TYPE_CHECKING, cast

from pipelex import builder, log
from pipelex.builder.builder import (
    PipelexBundleSpec,
    PipeSpecUnion,
    reconstruct_bundle_with_pipe_fixes,
)
from pipelex.builder.builder_errors import PipeBuilderError
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.exceptions import PipelexBundleSpecBlueprintError
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.client.protocol import PipelineInputs
from pipelex.config import get_config
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.exceptions import PipeFactoryErrorType, PipeValidationErrorType
from pipelex.core.pipes.pipe_blueprint import PipeCategory
from pipelex.core.pipes.variable_multiplicity import format_concept_with_multiplicity, parse_concept_with_multiplicity
from pipelex.graph.graphspec import GraphSpec
from pipelex.hub import get_required_pipe
from pipelex.language.plx_factory import PlxFactory
from pipelex.pipeline.execute import execute_pipeline
from pipelex.pipeline.validate_bundle import ValidateBundleError, validate_bundle
from pipelex.system.configuration.configs import PipelineExecutionConfig
from pipelex.tools.misc.file_utils import get_incremental_file_path, save_text_to_path
from pipelex.tools.misc.json_utils import save_as_json_to_path

if TYPE_CHECKING:
    from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition


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
            save_as_json_to_path(object_to_save=pipe_output.working_memory.smart_dump(), path=str(working_memory_path), create_directory=True)

        pipelex_bundle_spec = pipe_output.working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)

        if is_save_first_iteration_enabled:
            try:
                plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
                first_iteration_path = get_incremental_file_path(
                    base_path=output_dir or "results/pipe-builder",
                    base_name="generated_pipeline_1st_iteration",
                    extension="plx",
                )
                save_text_to_path(text=plx_content, path=str(first_iteration_path), create_directory=True)
            except PipelexBundleSpecBlueprintError as exc:
                log.warning(f"Could not save first iteration PLX: {exc}")

        max_attempts = get_config().pipelex.builder_config.fix_loop_max_attempts
        for attempt in range(1, max_attempts + 1):
            # Phase 1: Create blueprint from spec
            try:
                bundle_blueprint = pipelex_bundle_spec.to_blueprint()
            except PipelexBundleSpecBlueprintError as exc:
                if attempt < max_attempts:
                    log.info(f"⚠️ Blueprint creation failed on attempt {attempt}/{max_attempts}, fixing undeclared concepts...")
                    pipelex_bundle_spec = await self._fix_undeclared_concept_references(pipelex_bundle_spec=pipelex_bundle_spec)
                    continue
                msg = f"Failed to create bundle blueprint after {max_attempts} attempts: {exc}"
                raise PipeBuilderError(msg) from exc

            # Phase 2: Validate the bundle
            try:
                await validate_bundle(blueprints=[bundle_blueprint])
                if attempt > 1:
                    log.info(f"✅ Bundle validation passed after fixes (attempt {attempt}/{max_attempts})")
                break  # Validation passed
            except ValidateBundleError as exc:
                if attempt < max_attempts:
                    log.info(f"⚠️ Validation failed on attempt {attempt}/{max_attempts}, attempting fixes...")
                    pipelex_bundle_spec = self._fix_bundle_validation_error(
                        bundle_error=exc, pipelex_bundle_spec=pipelex_bundle_spec, is_save_second_iteration_enabled=is_save_second_iteration_enabled
                    )
                else:
                    log.error(f"❌ Validation failed after {max_attempts} attempts, raising error")
                    raise

        return pipelex_bundle_spec, pipe_output.graph_spec

    async def _fix_undeclared_concept_references(
        self,
        pipelex_bundle_spec: PipelexBundleSpec,
    ) -> PipelexBundleSpec:
        """Fix undeclared concept references in pipe specs.

        Collects all concept references from pipe specs, determines which are undeclared,
        fixes PipeParallel combined_output references deterministically, and generates
        ConceptSpec definitions for any remaining undeclared concepts via an LLM pipeline.
        """
        # Step 1: Collect all local concept references from pipe specs
        concept_references: list[tuple[str, str, str]] = []  # (concept_code, pipe_code, field_context)
        if pipelex_bundle_spec.pipe:
            for pipe_code, pipe_spec in pipelex_bundle_spec.pipe.items():
                # Parse output
                output_parse = parse_concept_with_multiplicity(pipe_spec.output)
                output_concept = output_parse.concept_ref_or_code
                if "." not in output_concept or output_concept.split(".")[0] == pipelex_bundle_spec.domain:
                    bare_code = output_concept.split(".")[-1] if "." in output_concept else output_concept
                    concept_references.append((bare_code, pipe_code, "output"))

                # Parse inputs
                if pipe_spec.inputs:
                    for input_name, input_concept_str in pipe_spec.inputs.items():
                        input_parse = parse_concept_with_multiplicity(input_concept_str)
                        input_concept = input_parse.concept_ref_or_code
                        if "." not in input_concept or input_concept.split(".")[0] == pipelex_bundle_spec.domain:
                            bare_code = input_concept.split(".")[-1] if "." in input_concept else input_concept
                            concept_references.append((bare_code, pipe_code, f"input '{input_name}'"))

                # Parse PipeParallel combined_output
                if isinstance(pipe_spec, PipeParallelSpec) and pipe_spec.combined_output:
                    combined_parse = parse_concept_with_multiplicity(pipe_spec.combined_output)
                    combined_concept = combined_parse.concept_ref_or_code
                    if "." not in combined_concept or combined_concept.split(".")[0] == pipelex_bundle_spec.domain:
                        bare_code = combined_concept.split(".")[-1] if "." in combined_concept else combined_concept
                        concept_references.append((bare_code, pipe_code, "combined_output"))

        # Step 2: Determine which are undeclared
        declared_concepts: set[str] = set()
        if pipelex_bundle_spec.concept:
            declared_concepts = set(pipelex_bundle_spec.concept.keys())
        native_concept_codes = {native.value for native in NativeConceptCode.values_list()}

        undeclared: set[str] = set()
        undeclared_refs: list[tuple[str, str, str]] = []
        for concept_code, pipe_code, field_context in concept_references:
            if concept_code not in declared_concepts and concept_code not in native_concept_codes:
                undeclared.add(concept_code)
                undeclared_refs.append((concept_code, pipe_code, field_context))

        if not undeclared:
            return pipelex_bundle_spec

        log.info(f"🔍 Found {len(undeclared)} undeclared concept(s): {', '.join(sorted(undeclared))}")

        # Step 3: Fix PipeParallel combined_output deterministically (no pipeline needed)
        fixed_pipe_parallel_concepts: set[str] = set()
        if pipelex_bundle_spec.pipe:
            for pipe_code, pipe_spec in pipelex_bundle_spec.pipe.items():
                if not isinstance(pipe_spec, PipeParallelSpec):
                    continue
                if not pipe_spec.combined_output:
                    continue

                combined_parse = parse_concept_with_multiplicity(pipe_spec.combined_output)
                combined_concept = combined_parse.concept_ref_or_code
                bare_combined = combined_concept.split(".")[-1] if "." in combined_concept else combined_concept

                if bare_combined not in undeclared:
                    continue

                if pipe_spec.add_each_output:
                    log.info(f"🔧 Removing undeclared combined_output '{pipe_spec.combined_output}' from PipeParallel '{pipe_code}'")
                    pipe_spec.combined_output = None
                    fixed_pipe_parallel_concepts.add(bare_combined)

                    # Also fix output if it references an undeclared concept
                    output_parse = parse_concept_with_multiplicity(pipe_spec.output)
                    output_concept = output_parse.concept_ref_or_code
                    bare_output = output_concept.split(".")[-1] if "." in output_concept else output_concept
                    if bare_output in undeclared:
                        log.info(f"🔧 Setting output of PipeParallel '{pipe_code}' to 'Anything'")
                        pipe_spec.output = "Anything"
                        fixed_pipe_parallel_concepts.add(bare_output)

        undeclared -= fixed_pipe_parallel_concepts

        # Step 4: Create remaining undeclared concepts via pipeline
        if undeclared:
            # Build context for the LLM
            lines: list[str] = ["Missing concepts that need to be defined:\n"]
            for concept_code, pipe_code, field_context in undeclared_refs:
                if concept_code in undeclared:
                    lines.append(f"- '{concept_code}' referenced in pipe '{pipe_code}' ({field_context})")

            lines.append("\nExisting declared concepts for context:")
            if pipelex_bundle_spec.concept:
                for concept_code, concept_spec_or_name in pipelex_bundle_spec.concept.items():
                    if isinstance(concept_spec_or_name, ConceptSpec):
                        lines.append(f"- {concept_code}: {concept_spec_or_name.description}")
                    else:
                        lines.append(f"- {concept_code}: {concept_spec_or_name}")
            else:
                lines.append("- (none)")

            undeclared_concepts = "\n".join(lines)
            log.info(f"🤖 Generating ConceptSpec definitions for {len(undeclared)} undeclared concept(s) via LLM...")

            concept_fixer_output = await execute_pipeline(
                pipe_code="generate_missing_concepts",
                library_dirs=[str(Path(builder.__file__).parent / "concept")],
                inputs={"undeclared_concepts": undeclared_concepts},
            )

            generated_concepts_list = concept_fixer_output.working_memory.get_stuff_as_list(
                name="generate_missing_concepts",
                item_type=ConceptSpec,
            )

            if pipelex_bundle_spec.concept is None:
                pipelex_bundle_spec.concept = {}

            for concept_spec in generated_concepts_list.items:
                pipelex_bundle_spec.concept[concept_spec.the_concept_code] = concept_spec
                log.info(f"🔧 Added generated concept '{concept_spec.the_concept_code}' to bundle")

        return pipelex_bundle_spec

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
                    if isinstance(pipe_spec, PipeSequenceSpec):
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

                    # Fix output concept for PipeCondition by checking mapped pipes' outputs
                    elif isinstance(pipe_spec, PipeConditionSpec):
                        # Get the PipeCondition instance to access pipe_dependencies()
                        pipe_condition = cast("PipeCondition", get_required_pipe(pipe_code=val_error.pipe_code))
                        mapped_pipe_codes = pipe_condition.pipe_dependencies()

                        if not mapped_pipe_codes:
                            # No mapped pipes (all special outcomes), any output is fine
                            continue

                        # Collect all unique output concept refs from mapped pipes
                        mapped_output_refs: set[str] = set()
                        for mapped_pipe_code in mapped_pipe_codes:
                            mapped_pipe = get_required_pipe(pipe_code=mapped_pipe_code)
                            mapped_output_refs.add(mapped_pipe.output.concept.concept_ref)

                        old_output = pipe_spec.output

                        # If all mapped pipes have same output, use that; otherwise use Anything
                        if len(mapped_output_refs) == 1:
                            new_output = next(iter(mapped_output_refs))
                        else:
                            new_output = "native.Anything"

                        pipe_spec.output = new_output
                        fixed_pipes.append(pipe_spec)
                        log.info(
                            f"🔧 Fixed output concept for PipeCondition '{val_error.pipe_code}': output changed from '{old_output}' → '{new_output}'"
                        )

                case (
                    PipeValidationErrorType.LLM_OUTPUT_CANNOT_BE_IMAGE
                    | PipeValidationErrorType.IMG_GEN_INPUT_NOT_TEXT_COMPATIBLE
                    | PipeValidationErrorType.INVALID_PIPE_CODE_SYNTAX
                    | PipeValidationErrorType.UNKNOWN_VALIDATION_ERROR
                    | PipeValidationErrorType.CIRCULAR_DEPENDENCY_ERROR
                ):
                    continue

        # Reconstruct bundle if we made pipe changes
        if fixed_pipes:
            pipelex_bundle_spec = reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes)

        # Save second iteration if we made any changes (pipes or concepts)
        if (fixed_pipes or added_concepts) and is_save_second_iteration_enabled:
            try:
                plx_content = PlxFactory.make_plx_content(blueprint=pipelex_bundle_spec.to_blueprint())
                second_iteration_path = get_incremental_file_path(
                    base_path="results",
                    base_name="generated_pipeline_2nd_iteration",
                    extension="plx",
                )
                save_text_to_path(text=plx_content, path=str(second_iteration_path))
            except PipelexBundleSpecBlueprintError as exc:
                log.warning(f"Could not save second iteration PLX: {exc}")

        return pipelex_bundle_spec
