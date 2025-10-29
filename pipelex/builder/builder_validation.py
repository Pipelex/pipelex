from pipelex import log
from pipelex.builder.builder_errors import (
    ConceptDefinitionErrorData,
    ConceptSpecError,
    DomainFailure,
    PipeDefinitionErrorData,
    PipeFailure,
    PipeInputErrorData,
    PipelexBundleError,
    PipelexBundleUnexpectedError,
    PipeSpecError,
    StaticValidationErrorData,
    ValidateDryRunError,
)
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.exceptions import (
    ConceptLoadingError,
    DomainLoadingError,
    PipeInputError,
    PipeLoadingError,
    StaticValidationError,
)
from pipelex.hub import get_library_manager, get_required_pipe
from pipelex.pipe_run.dry_run import DryRunOutput, dry_run_pipes


async def validate_bundle_spec_from_memory(working_memory: WorkingMemory):
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    await validate_bundle_spec(bundle_spec=pipelex_bundle_spec)


def fix_inputs_consistency(bundle_spec: PipelexBundleSpec) -> PipelexBundleSpec:
    """Proactively fix input declarations for all PipeController pipes.

    This function rebuilds the inputs dict for all PipeController pipes (PipeSequence,
    PipeParallel, PipeCondition, PipeBatch) based on their actual requirements computed
    by the needed_inputs() method. This ensures consistency before validation.

    Args:
        bundle_spec: The bundle spec to fix.

    Returns:
        The modified bundle spec with fixed inputs.

    Raises:
        PipelexBundleError: If loading the bundle fails or other errors occur.
    """
    log.dev(f"🔧 Starting input consistency fix for domain '{bundle_spec.domain}'")

    if not bundle_spec.pipe:
        log.dev("No pipes found in bundle spec, skipping input consistency fix")
        return bundle_spec

    # Convert to blueprint and load into library
    try:
        bundle_blueprint = bundle_spec.to_blueprint()
    except ConceptSpecError as concept_spec_error:
        concept_failures = [concept_spec_error.concept_failure]
        raise PipelexBundleError(message=concept_spec_error.message, concept_failures=concept_failures) from concept_spec_error
    except PipeSpecError as pipe_spec_error:
        pipe_failures = [pipe_spec_error.pipe_failure]
        raise PipelexBundleError(message=pipe_spec_error.message, pipe_failures=pipe_failures) from pipe_spec_error

    log.dev(f"Loading bundle blueprint for domain '{bundle_spec.domain}' into library manager")
    library_manager = get_library_manager()
    try:
        library_manager.load_from_blueprint(blueprint=bundle_blueprint)
        log.dev(f"Successfully loaded bundle with {len(bundle_spec.pipe)} pipes")
    except StaticValidationError as static_validation_error:
        static_validation_error_data = StaticValidationErrorData(
            error_type=static_validation_error.error_type,
            domain=static_validation_error.domain,
            pipe_code=static_validation_error.pipe_code,
            variable_names=static_validation_error.variable_names,
            required_concept_codes=static_validation_error.required_concept_codes,
            provided_concept_code=static_validation_error.provided_concept_code,
            file_path=static_validation_error.file_path,
            explanation=static_validation_error.explanation,
        )
        raise PipelexBundleError(
            message=static_validation_error.desc(), static_validation_error=static_validation_error_data
        ) from static_validation_error
    except DomainLoadingError as domain_loading_error:
        domain_failures = [DomainFailure(domain_code=domain_loading_error.domain_code, error_message=str(domain_loading_error))]
        raise PipelexBundleError(message=domain_loading_error.message, domain_failures=domain_failures) from domain_loading_error
    except ConceptLoadingError as concept_loading_error:
        concept_def_error = concept_loading_error.concept_definition_error
        concept_definition_error_data = ConceptDefinitionErrorData(
            message=str(concept_def_error),
            domain_code=concept_def_error.domain_code,
            concept_code=concept_def_error.concept_code,
            description=concept_def_error.description,
            structure_class_python_code=concept_def_error.structure_class_python_code,
            structure_class_syntax_error_data=concept_def_error.structure_class_syntax_error_data,
            source=concept_def_error.source,
        )
        raise PipelexBundleError(
            message=concept_loading_error.message, concept_definition_errors=[concept_definition_error_data]
        ) from concept_loading_error
    except PipeLoadingError as pipe_loading_error:
        pipe_def_error = pipe_loading_error.pipe_definition_error
        pipe_definition_error_data = PipeDefinitionErrorData(
            message=str(pipe_def_error),
            domain_code=pipe_def_error.domain_code,
            pipe_code=pipe_def_error.pipe_code,
            description=pipe_def_error.description,
            source=pipe_def_error.source,
        )
        raise PipelexBundleError(message=pipe_loading_error.message, pipe_definition_errors=[pipe_definition_error_data]) from pipe_loading_error
    except PipeInputError as pipe_input_error:
        pipe_input_error_data = PipeInputErrorData(
            message=str(pipe_input_error),
            pipe_code=pipe_input_error.pipe_code,
            variable_name=pipe_input_error.variable_name,
            concept_code=pipe_input_error.concept_code,
        )
        raise PipelexBundleError(message=pipe_input_error.message, pipe_input_errors=[pipe_input_error_data]) from pipe_input_error

    # Fix inputs for all PipeController pipes
    log.dev("Starting to fix inputs for PipeController pipes")
    fixed_count = 0
    try:
        for pipe_code, pipe_spec in bundle_spec.pipe.items():
            # Check if this is a PipeController
            if AllowedPipeCategories.is_controller_by_str(category_str=pipe_spec.pipe_category):
                log.dev(f"  Checking inputs for {pipe_spec.type} pipe '{pipe_code}'")

                # Get the loaded pipe instance
                pipe = get_required_pipe(pipe_code=pipe_code)

                # Get the actual needed inputs
                needed_inputs = pipe.needed_inputs()

                # Store old inputs for logging
                old_inputs = pipe_spec.inputs.copy()

                # Rebuild the inputs dict from needed_inputs, preserving multiplicity
                new_inputs: dict[str, str] = {}
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
                    new_inputs[named_requirement.variable_name] = concept_code

                # Update the pipe spec inputs
                pipe_spec.inputs = new_inputs

                # Log the changes
                if old_inputs != new_inputs:
                    log.dev(f"    Old inputs: {old_inputs}")
                    log.dev(f"    New inputs: {new_inputs}")
                    fixed_count += 1
                else:
                    log.dev("    ✅")
    finally:
        # Clean up by removing the bundle from library manager
        log.dev("Cleaning up: removing bundle from library manager")
        library_manager.remove_from_blueprint(blueprint=bundle_blueprint)

    log.dev(f"✅ Input consistency fix completed: fixed {fixed_count} PipeController pipe(s)")
    return bundle_spec


async def validate_bundle_spec(bundle_spec: PipelexBundleSpec):
    try:
        bundle_blueprint = bundle_spec.to_blueprint()
    except ConceptSpecError as concept_spec_error:
        concept_failures = [concept_spec_error.concept_failure]
        raise PipelexBundleError(message=concept_spec_error.message, concept_failures=concept_failures) from concept_spec_error
    except PipeSpecError as pipe_spec_error:
        pipe_failures = [pipe_spec_error.pipe_failure]
        raise PipelexBundleError(message=pipe_spec_error.message, pipe_failures=pipe_failures) from pipe_spec_error

    library_manager = get_library_manager()
    dry_run_result = await dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
    library_manager.remove_from_blueprint(blueprint=bundle_blueprint)

    dry_run_pipe_failures = extract_pipe_failures_from_dry_run_result(bundle_spec=bundle_spec, dry_run_result=dry_run_result)
    if dry_run_pipe_failures:
        raise PipelexBundleError(message="Pipes failed during dry run", pipe_failures=dry_run_pipe_failures)


def extract_pipe_failures_from_dry_run_result(bundle_spec: PipelexBundleSpec, dry_run_result: dict[str, DryRunOutput]) -> list[PipeFailure]:
    dry_run_pipe_failures: list[PipeFailure] = []
    for pipe_code, dry_run_output in dry_run_result.items():
        if dry_run_output.status.is_failure:
            if not bundle_spec.pipe:
                msg = f"No pipes section found in bundle spec but we recorded a dry run failure for pipe '{pipe_code}'"
                raise PipelexBundleUnexpectedError(message="No pipes section found in bundle spec")
            if pipe_code not in bundle_spec.pipe:
                msg = f"Pipe '{pipe_code}' not found in bundle spec but we recorded a dry run failure for it"
                raise PipelexBundleUnexpectedError(message=msg)

            pipe_spec = bundle_spec.pipe[pipe_code]
            spec_class = pipe_type_to_spec_class.get(pipe_spec.type)
            if not spec_class:
                msg = f"Unknown pipe type: {pipe_spec.type}"
                raise ValidateDryRunError(msg)
            pipe_spec = spec_class(**pipe_spec.model_dump(serialize_as_any=True))
            pipe_failure = PipeFailure(
                pipe_spec=pipe_spec,
                error_message=dry_run_output.error_message or "",
            )
            dry_run_pipe_failures.append(pipe_failure)
    return dry_run_pipe_failures


def document_pipe_failures_from_dry_run_blueprint(
    bundle_blueprint: PipelexBundleBlueprint, dry_run_result: dict[str, DryRunOutput]
) -> list[PipeFailure]:
    dry_run_pipe_failures: list[PipeFailure] = []
    for pipe_code, dry_run_output in dry_run_result.items():
        if dry_run_output.status.is_failure:
            if not bundle_blueprint.pipe:
                msg = f"No pipes section found in bundle spec but we recorded a dry run failure for pipe '{pipe_code}'"
                raise PipelexBundleUnexpectedError(message="No pipes section found in bundle spec")
            if pipe_code not in bundle_blueprint.pipe:
                msg = f"Pipe '{pipe_code}' not found in bundle spec but we recorded a dry run failure for it"
                raise PipelexBundleUnexpectedError(message=msg)

            pipe_spec = bundle_blueprint.pipe[pipe_code]
            spec_class = pipe_type_to_spec_class.get(pipe_spec.type)
            if not spec_class:
                msg = f"Unknown pipe type: {pipe_spec.type}"
                raise ValidateDryRunError(msg)
            pipe_spec = spec_class(**pipe_spec.model_dump(serialize_as_any=True))
            pipe_failure = PipeFailure(
                pipe_spec=pipe_spec,
                error_message=dry_run_output.error_message or "",
            )
            dry_run_pipe_failures.append(pipe_failure)
    return dry_run_pipe_failures


async def dry_run_bundle_blueprint(bundle_blueprint: PipelexBundleBlueprint) -> dict[str, DryRunOutput]:
    library_manager = get_library_manager()
    try:
        pipes = library_manager.load_from_blueprint(blueprint=bundle_blueprint)
        dry_run_result = await dry_run_pipes(pipes=pipes, raise_on_failure=True)
    except StaticValidationError as static_validation_error:
        static_validation_error_data = StaticValidationErrorData(
            error_type=static_validation_error.error_type,
            domain=static_validation_error.domain,
            pipe_code=static_validation_error.pipe_code,
            variable_names=static_validation_error.variable_names,
            required_concept_codes=static_validation_error.required_concept_codes,
            provided_concept_code=static_validation_error.provided_concept_code,
            file_path=static_validation_error.file_path,
            explanation=static_validation_error.explanation,
        )
        raise PipelexBundleError(
            message=static_validation_error.desc(), static_validation_error=static_validation_error_data
        ) from static_validation_error
    except DomainLoadingError as domain_loading_error:
        domain_failures = [DomainFailure(domain_code=domain_loading_error.domain_code, error_message=str(domain_loading_error))]
        raise PipelexBundleError(message=domain_loading_error.message, domain_failures=domain_failures) from domain_loading_error
    except ConceptLoadingError as concept_loading_error:
        concept_def_error = concept_loading_error.concept_definition_error
        concept_definition_error_data = ConceptDefinitionErrorData(
            message=str(concept_def_error),
            domain_code=concept_def_error.domain_code,
            concept_code=concept_def_error.concept_code,
            description=concept_def_error.description,
            structure_class_python_code=concept_def_error.structure_class_python_code,
            structure_class_syntax_error_data=concept_def_error.structure_class_syntax_error_data,
            source=concept_def_error.source,
        )
        raise PipelexBundleError(
            message=concept_loading_error.message, concept_definition_errors=[concept_definition_error_data]
        ) from concept_loading_error
    except PipeLoadingError as pipe_loading_error:
        pipe_def_error = pipe_loading_error.pipe_definition_error
        pipe_definition_error_data = PipeDefinitionErrorData(
            message=str(pipe_def_error),
            domain_code=pipe_def_error.domain_code,
            pipe_code=pipe_def_error.pipe_code,
            description=pipe_def_error.description,
            source=pipe_def_error.source,
        )
        raise PipelexBundleError(message=pipe_loading_error.message, pipe_definition_errors=[pipe_definition_error_data]) from pipe_loading_error
    except PipeInputError as pipe_input_error:
        pipe_input_error_data = PipeInputErrorData(
            message=str(pipe_input_error),
            pipe_code=pipe_input_error.pipe_code,
            variable_name=pipe_input_error.variable_name,
            concept_code=pipe_input_error.concept_code,
        )
        raise PipelexBundleError(message=pipe_input_error.message, pipe_input_errors=[pipe_input_error_data]) from pipe_input_error
    return dry_run_result


async def validate_dry_run_bundle_blueprint(bundle_blueprint: PipelexBundleBlueprint):
    dry_run_result = await dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
    pipe_failures = document_pipe_failures_from_dry_run_blueprint(bundle_blueprint=bundle_blueprint, dry_run_result=dry_run_result)
    if pipe_failures:
        msg = "Dry run failed for bundle"
        raise PipelexBundleError(message=msg, pipe_failures=pipe_failures)
