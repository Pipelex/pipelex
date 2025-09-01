from typing import Annotated, Dict, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.jinja2.pipe_jinja2_blueprint import PipeJinja2Blueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.ocr.pipe_ocr_blueprint import PipeOcrBlueprint

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


class PipelexBundleBlueprint(BaseModel):
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

    concept: Optional[Dict[str, ConceptBlueprint | str]] = Field(default_factory=dict)

    pipe: Optional[Dict[str, PipeBlueprintUnion]] = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain
