from typing import Annotated, cast

from pydantic import ConfigDict, Field, ValidationError, field_validator

from pipelex.core.bundles.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent
from pipelex.hub import get_library_manager
from pipelex.libraries.pipelines.builder.concept.concept_spec import ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_batch_spec import PipeBatchSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_condition_spec import PipeConditionSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_func_spec import PipeFuncSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_img_spec import PipeImgGenSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2_spec import PipeJinja2Spec
from pipelex.libraries.pipelines.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_ocr_spec import PipeOcrSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_parallel_spec import PipeParallelSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.libraries.pipelines.builder.pipe.pipe_signature import PipeSignature
from pipelex.pipe_works.pipe_dry import dry_run_pipes
from pipelex.tools.typing.pydantic_utils import empty_list_factory_of, format_pydantic_validation_error
from pipelex.types import StrEnum


class DomainInformation(StructuredContent):
    domain: str = Field(description="The domain of the pipeline library.")
    definition: str = Field(description="The definition of the pipeline library.")


class PipeBuilderError(Exception):
    pass


class PipelexBundleSpecDraft(StructuredContent):
    """Complete spec of a pipeline library TOML file."""

    domain: str = Field(description="The domain of the pipeline library.")
    definition: str = Field(description="The definition of the pipeline library.")

    concept: dict[str, ConceptSpec] = Field(default_factory=dict, description="The concepts of the pipeline library.")

    pipe: dict[str, PipeSignature] = Field(default_factory=dict, description="The pipes of the pipeline library.")


PipeSpecUnion = Annotated[
    PipeFuncSpec
    | PipeImgGenSpec
    | PipeJinja2Spec
    | PipeLLMSpec
    | PipeOcrSpec
    | PipeBatchSpec
    | PipeConditionSpec
    | PipeParallelSpec
    | PipeSequenceSpec,
    Field(discriminator="type"),
]


class PipelexBundleSpec(StructuredContent):
    """Complete spec of a Pipelex bundle TOML definition.

    Represents the top-level structure of a Pipelex bundle, which defines a domain
    with its concepts, pipes, and configuration. Bundles are the primary unit of
    organization for Pipelex workflows, loaded from TOML files.

    Attributes:
        domain: The domain identifier for this bundle in snake_case format.
               Serves as the namespace for all concepts and pipes within.
        definition: Natural language description of the pipeline's purpose and functionality.
        system_prompt: Default system prompt applied to all LLM pipes in the bundle
                      unless overridden at the pipe level.
        system_prompt_to_structure: System prompt specifically for output structuring
                                   operations across the bundle.
        prompt_template_to_structure: Template for structuring prompts used in output
                                     formatting operations.
        concept: Dictionary of concept definitions used in this domain. Keys are concept
                codes in PascalCase format, values are ConceptBlueprint instances or
                string references to existing concepts.
        pipe: Dictionary of pipe definitions for data transformation. Keys are pipe
             codes in snake_case format, values are specific pipe spec types
             (PipeLLM, PipeImgGen, PipeSequence, etc.).

    Validation Rules:
        1. Domain must be in valid snake_case format.
        2. Concept keys must be in PascalCase format.
        3. Pipe keys must be in snake_case format.
        4. Extra fields are forbidden (strict mode).
        5. Pipe types must match their blueprint discriminator.

    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    definition: str | None = None
    system_prompt: str | None = None
    system_prompt_to_structure: str | None = None
    prompt_template_to_structure: str | None = None

    concept: dict[str, ConceptSpec | str] | None = Field(default_factory=dict)

    pipe: dict[str, PipeSpecUnion] | None = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain

    def to_blueprint(self) -> PipelexBundleBlueprint:
        concept: dict[str, ConceptBlueprint | str] | None = None

        if self.concept:
            concept = {}
            for concept_code, concept_blueprint in self.concept.items():
                if isinstance(concept_blueprint, ConceptSpec):
                    concept[concept_code] = concept_blueprint.to_blueprint()
                else:
                    concept[concept_code] = ConceptBlueprint(definition=concept_code, structure=concept_blueprint)

        pipe: dict[str, PipeBlueprintUnion] | None = None
        if self.pipe:
            pipe = {}
            for pipe_code, pipe_blueprint in self.pipe.items():
                pipe[pipe_code] = pipe_blueprint.to_blueprint()

        return PipelexBundleBlueprint(
            domain=self.domain,
            definition=self.definition,
            prompt_template_to_structure=self.prompt_template_to_structure,
            system_prompt=self.system_prompt,
            system_prompt_to_structure=self.system_prompt_to_structure,
            pipe=pipe,
            concept=concept,
        )


# TODO: Put this in a factory. Investigate why it is necessary.
def _convert_pipe_spec(pipe_spec: PipeSpecUnion) -> PipeSpecUnion:
    pipe_type_to_class: dict[str, type] = {
        "PipeFunc": PipeFuncSpec,
        "PipeImgGen": PipeImgGenSpec,
        "PipeJinja2": PipeJinja2Spec,
        "PipeLLM": PipeLLMSpec,
        "PipeOcr": PipeOcrSpec,
        "PipeBatch": PipeBatchSpec,
        "PipeCondition": PipeConditionSpec,
        "PipeParallel": PipeParallelSpec,
        "PipeSequence": PipeSequenceSpec,
    }

    pipe_class = pipe_type_to_class.get(pipe_spec.type)
    if pipe_class is None:
        msg = f"Unknown pipe type: {pipe_spec.type}"
        raise PipeBuilderError(msg)
    return cast("PipeSpecUnion", pipe_class(**pipe_spec.model_dump(serialize_as_any=True)))


async def compile_in_pipelex_bundle_spec(working_memory: WorkingMemory) -> PipelexBundleSpec:
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

    pipe_specs = cast("ListContent[PipeSpecUnion]", working_memory.get_stuff(name="pipe_specs").content)
    domain_information = working_memory.get_stuff_as(name="domain_information", content_type=DomainInformation)

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
        domain=domain_information.domain,
        definition=domain_information.definition,
        concept=validated_concepts,
        pipe={pipe_spec.the_pipe_code: _convert_pipe_spec(pipe_spec) for pipe_spec in pipe_specs.items},
    )


# TODO: rename or merge with PipeDry.DryRunStatus
class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ValidateDryRunError(Exception):
    """Raised when validating the dry run of a pipelex bundle blueprint."""


class PipeFailure(StructuredContent):
    """Details of a single pipe failure during dry run."""

    pipe: PipeSpecUnion = Field(description="The failing pipe spec blueprint with pipe code")
    error_message: str = Field(description="The error message for this pipe")


class DryRunResult(StructuredContent):
    """A result of a dry run of a pipelex bundle blueprint."""

    status: DryRunStatus
    failed_pipes: list[PipeFailure] = Field(
        default_factory=empty_list_factory_of(PipeFailure),
        description="List of pipes that failed during dry run",
    )


async def validate_dry_run(working_memory: WorkingMemory) -> ListContent[PipeFailure]:
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    pipelex_bundle_blueprint = pipelex_bundle_spec.to_blueprint()

    library_manager = get_library_manager()

    pipes = library_manager.load_from_blueprint(blueprint=pipelex_bundle_blueprint)
    dry_run_result = await dry_run_pipes(pipes=pipes, raise_on_failure=False)
    library_manager.remove_from_blueprint(blueprint=pipelex_bundle_blueprint)

    pipe_type_to_spec_class = {
        "PipeFunc": PipeFuncSpec,
        "PipeImgGen": PipeImgGenSpec,
        "PipeJinja2": PipeJinja2Spec,
        "PipeLLM": PipeLLMSpec,
        "PipeOcr": PipeOcrSpec,
        "PipeBatch": PipeBatchSpec,
        "PipeCondition": PipeConditionSpec,
        "PipeParallel": PipeParallelSpec,
        "PipeSequence": PipeSequenceSpec,
    }

    failed_pipes: list[PipeFailure] = []
    for pipe_code, dry_run_output in dry_run_result.items():
        if dry_run_output.status.is_failure and pipelex_bundle_spec.pipe and pipe_code in pipelex_bundle_spec.pipe:
            pipe_spec = pipelex_bundle_spec.pipe[pipe_code]
            spec_class = pipe_type_to_spec_class.get(pipe_spec.type)
            if not spec_class:
                msg = f"Unknown pipe type: {pipe_spec.type}"
                raise ValidateDryRunError(msg)
            pipe_spec = spec_class(**pipe_spec.model_dump(serialize_as_any=True))
            failed_pipes.append(
                PipeFailure(
                    pipe=pipe_spec,
                    error_message=dry_run_output.error_message or "",
                ),
            )

    return ListContent[PipeFailure](items=failed_pipes)


async def reconstruct_bundle_with_all_fixes(working_memory: WorkingMemory) -> PipelexBundleSpec:
    pipelex_bundle_spec = working_memory.get_stuff_as(name="pipelex_bundle_spec", content_type=PipelexBundleSpec)
    fixed_pipes_list = cast("ListContent[PipeSpecUnion]", working_memory.get_stuff(name="fixed_pipes").content)

    if not pipelex_bundle_spec.pipe:
        msg = "No pipes section found in bundle spec"
        raise PipeBuilderError(msg)

    for fixed_pipe_blueprint in fixed_pipes_list.items:
        pipe_code = fixed_pipe_blueprint.the_pipe_code
        pipelex_bundle_spec.pipe[pipe_code] = fixed_pipe_blueprint

    return pipelex_bundle_spec
