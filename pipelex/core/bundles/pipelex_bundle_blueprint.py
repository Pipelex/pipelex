from typing import Annotated, Any, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from pipelex.core.bundles.exceptions import PipelexBundleBlueprintError
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
    """Complete blueprint of a pipelex bundle TOML definition."""

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

    @model_validator(mode="before")
    @classmethod
    def validate_non_valid_values_in_blueprint(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # TODO: to test
        for key in values.keys():
            if key not in ["domain", "definition", "system_prompt", "system_prompt_to_structure", "prompt_template_to_structure", "concept", "pipe"]:
                raise PipelexBundleBlueprintError(f"Invalid key '{key}' in bundle blueprint")
        return values
