from typing import Annotated, Any, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from pipelex.core.bundles.exceptions import PipelexBundleBlueprintError
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain import DomainBlueprint
from pipelex.pipe_controllers.pipe_batch_factory import PipeBatchBlueprint
from pipelex.pipe_controllers.pipe_condition_factory import PipeConditionBlueprint
from pipelex.pipe_controllers.pipe_parallel_factory import PipeParallelBlueprint
from pipelex.pipe_controllers.pipe_sequence_factory import PipeSequenceBlueprint
from pipelex.pipe_operators.pipe_func_factory import PipeFuncBlueprint
from pipelex.pipe_operators.pipe_img_gen_factory import PipeImgGenBlueprint
from pipelex.pipe_operators.pipe_jinja2_factory import PipeJinja2Blueprint
from pipelex.pipe_operators.pipe_llm_factory import PipeLLMBlueprint
from pipelex.pipe_operators.pipe_ocr_factory import PipeOcrBlueprint

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
