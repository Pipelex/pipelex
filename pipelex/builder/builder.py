from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from pipelex.builder.builder_errors import (
    ConceptDefinitionErrorData,
    ConceptSpecError,
    DomainFailure,
    PipeBuilderError,
    PipeDefinitionErrorData,
    PipeFailure,
    PipelexBundleError,
    PipelexBundleUnexpectedError,
    PipeSpecError,
    StaticValidationErrorData,
    ValidateDryRunError,
)
from pipelex.builder.bundle_header_spec import BundleHeaderSpec
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.builder.pipe.pipe_compose_spec import PipeComposeSpec
from pipelex.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.builder.pipe.pipe_extract_spec import PipeExtractSpec
from pipelex.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.builder.pipe.pipe_img_gen_spec import PipeImgGenSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.exceptions import (
    ConceptLoadingError,
    DomainLoadingError,
    PipeLoadingError,
    StaticValidationError,
)
from pipelex.hub import get_library_manager
from pipelex.pipe_run.dry_run import dry_run_pipes
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.stuffs.list_content import ListContent


# # TODO: Put this in a factory. Investigate why it is necessary.
def _convert_pipe_spec(pipe_spec: PipeSpecUnion) -> PipeSpecUnion:
    pipe_type_to_class: dict[str, type] = {
        "PipeFunc": PipeFuncSpec,
        "PipeImgGen": PipeImgGenSpec,
        "PipeCompose": PipeComposeSpec,
        "PipeLLM": PipeLLMSpec,
        "PipeExtract": PipeExtractSpec,
        "PipeBatch": PipeBatchSpec,
        "PipeCondition": PipeConditionSpec,
        "PipeParallel": PipeParallelSpec,
        "PipeSequence": PipeSequenceSpec,
    }

    pipe_class = pipe_type_to_class.get(pipe_spec.type)
    if pipe_class is None:
        msg = f"Unknown pipe type: {pipe_spec.type}"
        raise PipeBuilderError(msg)
    if not issubclass(pipe_class, PipeSpec):
        msg = f"Pipe class {pipe_class} is not a subclass of PipeSpec"
        raise PipeBuilderError(msg)
    return cast("PipeSpecUnion", pipe_class.model_validate(pipe_spec.model_dump(serialize_as_any=True)))


@pipe_func()
async def assemble_pipelex_bundle_spec(working_memory: WorkingMemory) -> PipelexBundleSpec:
    """Construct a PipelexBundleSpec from working memory containing concept and pipe blueprints.

    Args:
        working_memory: WorkingMemory containing concept_blueprints and pipe_blueprints stuffs.

    Returns:
        PipelexBundleSpec: The constructed pipeline spec.

    """
    # The working memory actually contains ConceptSpec objects (not ConceptSpecDraft)
    # but they may have been deserialized incorrectly
    concept_specs = working_memory.get_stuff_as_list(
        name="concept_specs",
        item_type=ConceptSpec,
    )

    pipe_specs: list[PipeSpecUnion] = cast("ListContent[PipeSpecUnion]", working_memory.get_stuff(name="pipe_specs").content).items
    bundle_header_spec = working_memory.get_stuff_as(name="bundle_header_spec", content_type=BundleHeaderSpec)

    # Properly validate and reconstruct concept specs to ensure proper Pydantic validation
    validated_concepts: dict[str, ConceptSpec | str] = {}
    for concept_spec in concept_specs.items:
        try:
            # Re-create the ConceptSpec to ensure proper Pydantic validation
            # This handles any serialization/deserialization issues from working memory
            validated_concept = ConceptSpec(**concept_spec.model_dump(serialize_as_any=True))
            validated_concepts[validated_concept.the_concept_code] = validated_concept
        except ValidationError as exc:
            msg = f"Failed to validate concept spec {concept_spec.the_concept_code}: {format_pydantic_validation_error(exc)}"
            raise PipeBuilderError(msg) from exc

    return PipelexBundleSpec(
        domain=bundle_header_spec.domain,
        description=bundle_header_spec.description,
        system_prompt=bundle_header_spec.system_prompt,
        main_pipe=bundle_header_spec.main_pipe,
        concept=validated_concepts,
        pipe={pipe_spec.pipe_code: _convert_pipe_spec(pipe_spec) for pipe_spec in pipe_specs},
    )


async def validate_bundle_spec_from_memory(working_memory: WorkingMemory):
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    await validate_bundle_spec(pipelex_bundle_spec=pipelex_bundle_spec)


async def validate_bundle_spec(pipelex_bundle_spec: PipelexBundleSpec):
    library_manager = get_library_manager()
    try:
        pipelex_bundle_blueprint = pipelex_bundle_spec.to_blueprint()
    except ConceptSpecError as concept_spec_error:
        concept_failures = [concept_spec_error.concept_failure]
        raise PipelexBundleError(message=concept_spec_error.message, concept_failures=concept_failures) from concept_spec_error
    except PipeSpecError as pipe_spec_error:
        pipe_failures = [pipe_spec_error.pipe_failure]
        raise PipelexBundleError(message=pipe_spec_error.message, pipe_failures=pipe_failures) from pipe_spec_error

    try:
        pipes = library_manager.load_from_blueprint(blueprint=pipelex_bundle_blueprint)
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

    library_manager.remove_from_blueprint(blueprint=pipelex_bundle_blueprint)

    pipe_type_to_spec_class = {
        "PipeFunc": PipeFuncSpec,
        "PipeImgGen": PipeImgGenSpec,
        "PipeCompose": PipeComposeSpec,
        "PipeLLM": PipeLLMSpec,
        "PipeExtract": PipeExtractSpec,
        "PipeBatch": PipeBatchSpec,
        "PipeCondition": PipeConditionSpec,
        "PipeParallel": PipeParallelSpec,
        "PipeSequence": PipeSequenceSpec,
    }

    dry_run_pipe_failures: list[PipeFailure] = []
    for pipe_code, dry_run_output in dry_run_result.items():
        if dry_run_output.status.is_failure:
            if not pipelex_bundle_spec.pipe:
                msg = f"No pipes section found in bundle spec but we recorded a dry run failure for pipe '{pipe_code}'"
                raise PipelexBundleUnexpectedError(message="No pipes section found in bundle spec")
            if pipe_code not in pipelex_bundle_spec.pipe:
                msg = f"Pipe '{pipe_code}' not found in bundle spec but we recorded a dry run failure for it"
                raise PipelexBundleUnexpectedError(message=msg)

            pipe_spec = pipelex_bundle_spec.pipe[pipe_code]
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
    if dry_run_pipe_failures:
        raise PipelexBundleError(message="Pipes failed during dry run", pipe_failures=dry_run_pipe_failures)


async def reconstruct_bundle_with_pipe_fixes_from_memory(working_memory: WorkingMemory) -> PipelexBundleSpec:
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    fixed_pipes_list = cast("ListContent[PipeSpecUnion]", working_memory.get_stuff(name="fixed_pipes").content)
    return reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec=pipelex_bundle_spec, fixed_pipes=fixed_pipes_list.items)


def reconstruct_bundle_with_pipe_fixes(pipelex_bundle_spec: PipelexBundleSpec, fixed_pipes: list[PipeSpecUnion]) -> PipelexBundleSpec:
    if not pipelex_bundle_spec.pipe:
        msg = "No pipes section found in bundle spec"
        raise PipelexBundleUnexpectedError(msg)

    for fixed_pipe_blueprint in fixed_pipes:
        pipe_code = fixed_pipe_blueprint.pipe_code
        pipelex_bundle_spec.pipe[pipe_code] = fixed_pipe_blueprint

    return pipelex_bundle_spec


async def reconstruct_bundle_with_all_fixes(working_memory: WorkingMemory) -> PipelexBundleSpec:
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    if fixed_pipes := working_memory.get_optional_stuff(name="fixed_pipes"):
        fixed_pipes_list = cast("ListContent[PipeSpecUnion]", fixed_pipes.content)

        if not pipelex_bundle_spec.pipe:
            msg = "No pipes section found in bundle spec"
            raise PipeBuilderError(msg)

        for fixed_pipe_blueprint in fixed_pipes_list.items:
            pipe_code = fixed_pipe_blueprint.pipe_code
            pipelex_bundle_spec.pipe[pipe_code] = fixed_pipe_blueprint

    if fixed_concepts := working_memory.get_optional_stuff(name="fixed_concepts"):
        fixed_concepts_list = cast("ListContent[ConceptSpec]", fixed_concepts.content)

        if not pipelex_bundle_spec.concept:
            msg = "No concepts section found in bundle spec"
            raise PipeBuilderError(msg)

        for fixed_concept_blueprint in fixed_concepts_list.items:
            concept_code = fixed_concept_blueprint.the_concept_code
            pipelex_bundle_spec.concept[concept_code] = fixed_concept_blueprint

    return pipelex_bundle_spec
