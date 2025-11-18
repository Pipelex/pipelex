from pipelex import log
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.core.pipes.pipe_blueprint import AllowedPipeCategories
from pipelex.hub import get_required_pipe
from pipelex.pipeline.validate_bundle import validate_bundle


async def fix_inputs_consistency(bundle_spec: PipelexBundleSpec) -> PipelexBundleSpec:
    """Proactively fix input declarations for all PipeController pipes.

    This function rebuilds the inputs dict for all PipeController pipes (PipeSequence,
    PipeParallel, PipeCondition, PipeBatch) based on their actual requirements computed
    by the needed_inputs() method. This ensures consistency before validation.

    Args:
        bundle_spec: The bundle spec to fix.

    Returns:
        The modified bundle spec with fixed inputs.
    """
    log.dev(f"🔧 Starting input consistency fix for domain '{bundle_spec.domain}'")

    if not bundle_spec.pipe:
        log.dev("No pipes found in bundle spec, skipping input consistency fix")
        return bundle_spec

    bundle_blueprint = bundle_spec.to_blueprint()
    await validate_bundle(blueprints=[bundle_blueprint])

    # Fix inputs for all PipeController pipes
    log.dev("Starting to fix inputs for PipeController pipes")
    fixed_count = 0
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

    log.dev(f"✅ Input consistency fix completed: fixed {fixed_count} PipeController pipe(s)")
    return bundle_spec

    # dry_run_pipe_failures = extract_pipe_failures_from_dry_run_result(bundle_spec=bundle_spec, dry_run_result=validate_bundle_result.dry_run_result)
    # if dry_run_pipe_failures:
    #     raise PipelexBundleError(message="Pipes failed during dry run", pipe_failures=dry_run_pipe_failures)


# def extract_pipe_failures_from_dry_run_result(bundle_spec: PipelexBundleSpec, dry_run_result: dict[str, DryRunOutput]) -> list[PipeFailure]:
#     dry_run_pipe_failures: list[PipeFailure] = []
#     for pipe_code, dry_run_output in dry_run_result.items():
#         if dry_run_output.status.is_failure:
#             if not bundle_spec.pipe:
#                 msg = f"No pipes section found in bundle spec but we recorded a dry run failure for pipe '{pipe_code}'"
#                 raise PipelexBundleUnexpectedError(message="No pipes section found in bundle spec")
#             if pipe_code not in bundle_spec.pipe:
#                 msg = f"Pipe '{pipe_code}' not found in bundle spec but we recorded a dry run failure for it"
#                 raise PipelexBundleUnexpectedError(message=msg)

#             pipe_spec = bundle_spec.pipe[pipe_code]
#             spec_class = pipe_type_to_spec_class.get(pipe_spec.type)
#             if not spec_class:
#                 msg = f"Unknown pipe type: {pipe_spec.type}"
#                 raise ValidateDryRunError(msg)
#             pipe_spec = spec_class(**pipe_spec.model_dump(serialize_as_any=True))
#             pipe_failure = PipeFailure(
#                 pipe_spec=pipe_spec,
#                 error_message=dry_run_output.error_message or "",
#             )
#             dry_run_pipe_failures.append(pipe_failure)
#     return dry_run_pipe_failures
