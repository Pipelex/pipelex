from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.compose.pipe_compose_blueprint import PipeComposeBlueprint
from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.img_gen.pipe_img_gen_blueprint import PipeImgGenBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint

PipeBlueprintUnion = Annotated[
    PipeFuncBlueprint
    | PipeImgGenBlueprint
    | PipeComposeBlueprint
    | PipeLLMBlueprint
    | PipeExtractBlueprint
    | PipeBatchBlueprint
    | PipeConditionBlueprint
    | PipeParallelBlueprint
    | PipeSequenceBlueprint,
    Field(discriminator="type"),
]


class PipelexBundleBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    domain: str
    description: str | None = None
    system_prompt: str | None = None
    system_prompt_to_structure: str | None = None
    prompt_template_to_structure: str | None = None

    concept: dict[str, ConceptBlueprint | str] | None = Field(default_factory=dict)

    pipe: dict[str, PipeBlueprintUnion] | None = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        DomainBlueprint.validate_domain_code(code=domain)
        return domain
