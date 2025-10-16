from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

from pipelex.builder.builder_errors import (
    PipeBuilderError,
    PipelexBundleError,
    PipelexBundleUnexpectedError,
)
from pipelex.builder.builder_validation import document_pipe_failures_from_dry_run_blueprint, dry_run_bundle_blueprint
from pipelex.builder.bundle_header_spec import BundleHeaderSpec
from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_signature import PipeSpec
from pipelex.builder.pipe.pipe_spec_map import pipe_type_to_spec_class
from pipelex.builder.pipe.pipe_spec_union import PipeSpecUnion
from pipelex.core.interpreter import PipelexInterpreter
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.list_content import ListContent
from pipelex.system.registries.func_registry import pipe_func
from pipelex.tools.typing.pydantic_utils import format_pydantic_validation_error

if TYPE_CHECKING:
    from pipelex.core.stuffs.list_content import ListContent


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


async def load_pipe_from_bundle(bundle_path: str) -> str:
    """Load a bundle file and extract its main_pipe.

    Args:
        bundle_path: Path to the .plx bundle file.

    Returns:
        The pipe_code from the bundle's main_pipe.

    Raises:
        FileNotFoundError: If the bundle file does not exist.
        PipelexBundleError: If no main_pipe is declared or if pipes fail during dry run.
        PipeInputError: If there are input errors during dry run validation.
    """
    bundle_path_obj = Path(bundle_path)
    if not bundle_path_obj.exists():
        msg = f"Bundle file not found: {bundle_path}"
        raise FileNotFoundError(msg)

    interpreter = PipelexInterpreter(file_path=bundle_path_obj)
    bundle_blueprint = interpreter.make_pipelex_bundle_blueprint()

    if not bundle_blueprint.main_pipe:
        msg = f"Bundle '{bundle_path}' does not declare a main_pipe"
        raise PipelexBundleError(message=msg)

    dry_run_result = await dry_run_bundle_blueprint(bundle_blueprint=bundle_blueprint)
    pipe_failures = document_pipe_failures_from_dry_run_blueprint(bundle_blueprint=bundle_blueprint, dry_run_result=dry_run_result)
    if pipe_failures:
        msg = f"Pipes failed during dry run in bundle '{bundle_path}'"
        raise PipelexBundleError(message=msg, pipe_failures=pipe_failures)

    return bundle_blueprint.main_pipe
