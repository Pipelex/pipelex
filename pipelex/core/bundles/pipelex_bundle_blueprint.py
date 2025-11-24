from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.exceptions import DomainCodeError
from pipelex.core.domains.validation import validate_domain_code
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
    main_pipe: str | None = None

    concept: dict[str, ConceptBlueprint | str] | None = Field(default_factory=dict)

    pipe: dict[str, PipeBlueprintUnion] | None = Field(default_factory=dict)

    @field_validator("domain", mode="before")
    @classmethod
    def validate_domain_syntax(cls, domain: str) -> str:
        # Then validate the domain code format
        try:
            validate_domain_code(code=domain)
        except DomainCodeError as exc:
            msg = f"Error when trying to validate the pipelex bundle at domain '{domain}': {exc}"
            raise ValueError(msg) from exc
        return domain

    @model_validator(mode="after")
    def validate_main_pipe(self) -> "PipelexBundleBlueprint":
        if self.main_pipe and (not self.pipe or (self.main_pipe not in self.pipe)):
            msg = f"Main pipe '{self.main_pipe}' could not be found in pipelex bundle at source '{self.source}' and domain '{self.domain}'"
            raise ValueError(msg)
        return self

    @property
    def nb_pipes(self) -> int:
        return len(self.pipe) if self.pipe else 0

    @property
    def nb_concepts(self) -> int:
        return len(self.concept) if self.concept else 0
