from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.concepts.validation import is_concept_code_valid
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
from pipelex.urls import URLs

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
    def validate_domain_syntax(cls, domain_code: str) -> str:
        try:
            validate_domain_code(code=domain_code)
        except DomainCodeError as exc:
            msg = f"Error when trying to validate the pipelex bundle at domain '{domain_code}': {exc}"
            raise ValueError(msg) from exc
        return domain_code

    @field_validator("concept", mode="before")
    @classmethod
    def validate_concept_keys(cls, concept: dict[str, ConceptBlueprint | str] | None) -> dict[str, ConceptBlueprint | str] | None:
        if concept is None:
            return None
        native_concept_codes = [native.value for native in NativeConceptCode.values_list()]
        for concept_code in concept:
            if not is_concept_code_valid(concept_code=concept_code):
                msg = f"Concept code '{concept_code}' is not a valid concept code"
                raise ValueError(msg)
            if concept_code in native_concept_codes:
                msg = (
                    f"Cannot declare a concept named '{concept_code}' because it is natively available in Pipelex. "
                    f"Native concepts are: {', '.join(native_concept_codes)}. "
                    f"See {URLs.native_concepts_docs}"
                )
                raise ValueError(msg)
        return concept

    @model_validator(mode="after")
    def validate_main_pipe(self) -> "PipelexBundleBlueprint":
        if self.main_pipe and (not self.pipe or (self.main_pipe not in self.pipe)):
            msg = f"Main pipe '{self.main_pipe}' could not be found in pipelex bundle at source '{self.source}' and domain '{self.domain}'"
            raise ValueError(msg)
        return self
