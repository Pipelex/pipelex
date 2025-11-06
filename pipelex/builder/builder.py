from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from pipelex import pretty_print
from pipelex.builder.builder_errors import (
    PipeBuilderError,
    PipelexBundleError,
    PipelexBundleUnexpectedError,
)
from pipelex.builder.builder_validation import validate_dry_run_bundle_blueprint
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
from pipelex.builder.pipe.pipe_spec import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.exceptions import StuffContentTypeError
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.stuffs.list_content import ListContent
    from pipelex.core.stuffs.stuff_content import StuffContent


# # TODO: Put this in a factory. Investigate why it is necessary.
def _convert_pipe_spec(pipe_spec: PipeSpecUnion) -> PipeSpecUnion:
    pipe_class = pipe_type_to_spec_class.get(pipe_spec.type)
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
    try:
        concept_specs = working_memory.get_stuff_as_list(
            name="concept_specs",
            item_type=ConceptSpec,
        )
    except StuffContentTypeError as exc:
        msg = f"assemble_pipelex_bundle_spec: Failed to get concept specs: {exc}."
        raise PipeBuilderError(message=msg, working_memory=working_memory) from exc
    # pipe_specs: list[PipeSpecUnion] = cast("ListContent[PipeSpecUnion]", working_memory.get_stuff(name="pipe_specs").content).items
    try:
        pipe_specs_list: ListContent[StuffContent] = working_memory.get_stuff_as_list(name="pipe_specs", item_type=StructuredContent)
    except StuffContentTypeError as exc:
        msg = f"assemble_pipelex_bundle_spec: Failed to get pipe specs: {exc}."
        raise PipeBuilderError(message=msg, working_memory=working_memory) from exc

    pipe_specs_list_items: list[StuffContent] = pipe_specs_list.items
    pipe_specs: list[PipeSpecUnion] = []
    for pipe_spec_item in pipe_specs_list_items:
        if not isinstance(
            pipe_spec_item,
            (
                PipeFuncSpec,
                PipeImgGenSpec,
                PipeComposeSpec,
                PipeLLMSpec,
                PipeExtractSpec,
                PipeBatchSpec,
                PipeConditionSpec,
                PipeParallelSpec,
                PipeSequenceSpec,
            ),
        ):
            msg = f"Pipe spec item '{pipe_spec_item}' is not any type of PipeSpecUnion, it's a {type(pipe_spec_item)}"
            raise PipeBuilderError(msg)
        pipe_specs.append(pipe_spec_item)

    bundle_header_spec = working_memory.get_stuff_as(name="bundle_header_spec", content_type=BundleHeaderSpec)

    # Properly validate and reconstruct concept specs to ensure proper Pydantic validation
    validated_concepts: dict[str, ConceptSpec | str] = {}
    for concept_spec in concept_specs.items:
        try:
            # Re-create the ConceptSpec to ensure proper Pydantic validation
            # This handles any serialization/deserialization issues from working memory
            validated_concept = ConceptSpec.model_validate(concept_spec.model_dump(serialize_as_any=True))
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


async def load_and_validate_bundle(bundle_path: str) -> PipelexBundleBlueprint:
    """Load a bundle file and extract its main_pipe.

    Args:
        bundle_path: Path to the .plx bundle file.

    Returns:
        PipelexBundleBlueprint: The blueprint of the bundle.

    Raises:
        PipelexBundleError: If any pipe failed during dry run.
    """
    bundle_blueprint = PipelexInterpreter.load_bundle_blueprint(bundle_path=bundle_path)

    try:
        await validate_dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
    except PipelexBundleError as exc:
        msg = f"Bundle at '{bundle_path}' failed to validate"
        pretty_print(exc, title="Validation Error Details")
        raise PipelexBundleError(message=msg, pipe_failures=exc.pipe_failures) from exc

    return bundle_blueprint
