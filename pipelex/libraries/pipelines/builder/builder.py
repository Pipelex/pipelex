from typing import Annotated, Dict, List, Optional, Union, cast

from pydantic import ConfigDict, Field, field_validator

from pipelex.core.bundles.pipelex_bundle_blueprint import (
    PipeBlueprintUnion as PipeBlueprintUnionCore,
)
from pipelex.core.bundles.pipelex_bundle_blueprint import (
    PipelexBundleBlueprint as PipelexBundleBlueprintCore,
)
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint as ConceptBlueprintCore
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_abstract import PipeAbstract
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent
from pipelex.hub import get_library_manager
from pipelex.libraries.pipelines.builder.concept.concept import ConceptBlueprint, ConceptSpec, ConceptSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeSignature
from pipelex.libraries.pipelines.builder.pipe.pipe_batch import PipeBatchBlueprint, PipeBatchSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_condition import PipeConditionBlueprint, PipeConditionSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_func import PipeFuncBlueprint, PipeFuncSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_img import PipeImgGenBlueprint, PipeImgGenSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_jinja2 import PipeJinja2Blueprint, PipeJinja2SpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_llm import PipeLLMBlueprint, PipeLLMSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_ocr import PipeOcrBlueprint, PipeOcrSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_parallel import PipeParallelBlueprint, PipeParallelSpecBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe_sequence import PipeSequenceBlueprint, PipeSequenceSpecBlueprint
from pipelex.pipe_works.pipe_dry import dry_run_pipes
from pipelex.types import StrEnum


class PipelexBundleBlueprintDraft(StructuredContent):
    """Complete blueprint of a pipeline library TOML file."""

    domain: str = Field(description="The domain of the pipeline library.")
    definition: str = Field(description="The definition of the pipeline library.")

    concept: Dict[str, ConceptSpec] = Field(default_factory=dict, description="The concepts of the pipeline library.")

    pipe: Dict[str, PipeSignature] = Field(default_factory=dict, description="The pipes of the pipeline library.")


PipeSpecBlueprintUnion = Annotated[
    Union[
        # Pipe operators
        PipeFuncSpecBlueprint,
        PipeImgGenSpecBlueprint,
        PipeJinja2SpecBlueprint,
        PipeLLMSpecBlueprint,
        PipeOcrSpecBlueprint,
        # Pipe controllers
        PipeBatchSpecBlueprint,
        PipeConditionSpecBlueprint,
        PipeParallelSpecBlueprint,
        PipeSequenceSpecBlueprint,
    ],
    Field(discriminator="type"),
]


PipeBlueprintUnion = Annotated[
    Union[
        # Pipe operators
        PipeFuncBlueprint,
        PipeImgGenBlueprint,
        PipeJinja2Blueprint,
        PipeLLMBlueprint,
        PipeOcrBlueprint,
        # Pipe controllers
        PipeBatchBlueprint,
        PipeConditionBlueprint,
        PipeParallelBlueprint,
        PipeSequenceBlueprint,
    ],
    Field(discriminator="type"),
]


class PipelexBundleBlueprint(StructuredContent):
    """Complete blueprint of a Pipelex bundle TOML definition.

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
             codes in snake_case format, values are specific pipe blueprint types
             (PipeLLM, PipeImgGen, PipeSequence, etc.).

    Validation Rules:
        1. Domain must be in valid snake_case format.
        2. Concept keys must be in PascalCase format.
        3. Pipe keys must be in snake_case format.
        4. Extra fields are forbidden (strict mode).
        5. Pipe types must match their blueprint discriminator.

    Raises:
        ValidationError: When domain, concept, or pipe naming conventions are violated.
        PipeDefinitionError: When pipe definitions are invalid.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    definition: Optional[str] = None
    system_prompt: Optional[str] = None
    system_prompt_to_structure: Optional[str] = None
    prompt_template_to_structure: Optional[str] = None

    concept: Optional[Dict[str, Union[ConceptBlueprint, str]]] = Field(default_factory=dict)

    pipe: Optional[Dict[str, PipeBlueprintUnion]] = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain

    def to_core_blueprint(self) -> PipelexBundleBlueprintCore:
        """Convert this PipelexBundleBlueprint to the core PipelexBundleBlueprint."""
        concept: Optional[Dict[str, Union[ConceptBlueprintCore, str]]] = None

        if self.concept:
            concept = {}
            for concept_code, concept_blueprint in self.concept.items():
                if isinstance(concept_blueprint, ConceptBlueprint):
                    concept[concept_code] = concept_blueprint.to_core_blueprint()
                else:
                    concept[concept_code] = ConceptBlueprintCore(definition=concept_code, structure=concept_blueprint)

        pipe: Optional[Dict[str, PipeBlueprintUnionCore]] = None
        if self.pipe:
            pipe = {}
            for pipe_code, pipe_blueprint in self.pipe.items():
                pipe_blueprint_typed: PipeBlueprintUnion = pipe_blueprint
                pipe[pipe_code] = pipe_blueprint_typed.to_core_blueprint(pipe_code, self.domain)

        return PipelexBundleBlueprintCore(
            domain=self.domain,
            definition=self.definition,
            prompt_template_to_structure=self.prompt_template_to_structure,
            system_prompt=self.system_prompt,
            system_prompt_to_structure=self.system_prompt_to_structure,
            pipe=pipe,
            concept=concept,
        )


def _convert_pipe_spec_to_blueprint(pipe_spec: PipeSpecBlueprintUnion) -> PipeBlueprintUnion:
    """Convert a PipeSpecBlueprint to the corresponding PipeBlueprint by removing the_pipe_code."""
    # First try with by_alias=True to get proper field names
    pipe_data = pipe_spec.model_dump(exclude={"the_pipe_code"}, by_alias=True)
    pipe_data["output"] = pipe_spec.output

    # Map pipe types to their blueprint classes
    pipe_type_to_class: Dict[str, type] = {
        "PipeFunc": PipeFuncBlueprint,
        "PipeImgGen": PipeImgGenBlueprint,
        "PipeJinja2": PipeJinja2Blueprint,
        "PipeLLM": PipeLLMBlueprint,
        "PipeOcr": PipeOcrBlueprint,
        "PipeBatch": PipeBatchBlueprint,
        "PipeCondition": PipeConditionBlueprint,
        "PipeParallel": PipeParallelBlueprint,
        "PipeSequence": PipeSequenceBlueprint,
    }

    pipe_class = pipe_type_to_class.get(pipe_spec.type)
    if pipe_class is None:
        raise ValueError(f"Unknown pipe type: {pipe_spec.type}")
    return cast(PipeBlueprintUnion, pipe_class(**pipe_data))


async def compile_in_pipelex_bundle_blueprint(working_memory: WorkingMemory) -> PipelexBundleBlueprint:
    """Construct a PipelexBundleBlueprint from working memory containing concept and pipe blueprints.

    Args:
        working_memory: WorkingMemory containing concept_blueprints and pipe_blueprints stuffs.

    Returns:
        PipelexBundleBlueprint: The constructed pipeline blueprint.
    """
    concept_blueprints = working_memory.get_stuff_as_list(
        name="concept_spec_blueprints",
        item_type=ConceptSpecBlueprint,
    )

    # Get pipe blueprints as ListContent directly and cast for typing
    # We can't use get_stuff_as_list with Union types, so we get the raw content
    pipe_spec_blueprints = cast(ListContent[PipeSpecBlueprintUnion], working_memory.get_stuff(name="pipe_spec_blueprints").content)

    return PipelexBundleBlueprint(
        domain="builder",
        definition="Builder pipeline library",
        concept={
            concept_spec_blueprint.the_concept_code: ConceptBlueprint(**concept_spec_blueprint.model_dump(exclude={"the_concept_code"}))
            for concept_spec_blueprint in concept_blueprints.items
        },
        pipe={
            pipe_spec_blueprint.the_pipe_code: _convert_pipe_spec_to_blueprint(pipe_spec_blueprint)
            for pipe_spec_blueprint in pipe_spec_blueprints.items
        },
    )


class DryRunStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class PipeFailure(StructuredContent):
    """Details of a single pipe failure during dry run."""

    pipe: PipeAbstract = Field(description="The failing pipe object")
    error_message: str = Field(description="The error message for this pipe")


class DryRunResult(StructuredContent):
    """A result of a dry run of a pipelex bundle blueprint."""

    status: DryRunStatus
    failed_pipes: List[PipeFailure] = Field(default_factory=list, description="List of pipes that failed during dry run")


async def validate_dry_run(working_memory: WorkingMemory) -> ListContent[PipeFailure]:
    """Validate a pipelex bundle blueprint and return list of failing pipes."""
    pipelex_bundle_blueprint = cast(
        PipelexBundleBlueprintCore, working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
    )

    library_manager = get_library_manager()
    pipes = library_manager.load_from_blueprint(blueprint=pipelex_bundle_blueprint)
    dry_run_result = await dry_run_pipes(pipes=pipes, error_on_failure=False)

    library_manager.remove_from_blueprint(blueprint=pipelex_bundle_blueprint)

    pipes_by_code = {pipe.code: pipe for pipe in pipes}

    # Collect ALL failing pipes with their actual pipe objects
    failed_pipes: List[PipeFailure] = []
    for pipe_code, dry_run_output in dry_run_result.items():
        if dry_run_output.status == DryRunStatus.FAILURE:
            pipe_object = pipes_by_code.get(pipe_code)
            if pipe_object:
                failed_pipes.append(
                    PipeFailure(
                        pipe=pipe_object,
                        error_message=dry_run_output.error_message or "",
                    )
                )

    return ListContent[PipeFailure](items=failed_pipes)


async def reconstruct_bundle_with_all_fixes(working_memory: WorkingMemory) -> PipelexBundleBlueprint:
    """Reconstruct the bundle blueprint with all the fixed pipes."""
    pipelex_bundle_blueprint = working_memory.get_stuff_as(name="pipelex_bundle_blueprint", content_type=PipelexBundleBlueprint)
    fixed_pipes_list = cast(ListContent[PipeSpecBlueprintUnion], working_memory.get_stuff(name="fixed_pipes").content)

    if not pipelex_bundle_blueprint.pipe:
        raise ValueError("No pipes section found in bundle blueprint")

    for fixed_pipe_blueprint in fixed_pipes_list.items:
        pipe_code = fixed_pipe_blueprint.the_pipe_code
        pipelex_bundle_blueprint.pipe[pipe_code] = _convert_pipe_spec_to_blueprint(fixed_pipe_blueprint)

    return pipelex_bundle_blueprint
