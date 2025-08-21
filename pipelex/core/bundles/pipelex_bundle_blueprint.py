import re
from typing import Annotated, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptBlueprintError
from pipelex.core.domains.domain import DomainBlueprint, DomainError
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
    def validate_domain_syntax(cls, domain: str) -> DomainBlueprint:
        if not re.match(r"^[a-z][a-z0-9_]*$", domain):
            raise DomainError(f"Domain must be snake_case (lowercase letters, numbers, and underscores only) for domain '{domain}': {domain}")
        return DomainBlueprint(code=domain)

    @field_validator("concept", mode="before")
    def transform_concept(cls, value: Dict[str, ConceptBlueprint | str]) -> Dict[str, ConceptBlueprint]:
        """Transform the concept declared as strings into ConceptBlueprint instances."""
        result: Dict[str, ConceptBlueprint] = {}

        for concept_code, concept_blueprint_or_str in value.items():
            if isinstance(concept_blueprint_or_str, str):
                result[concept_code] = ConceptBlueprint(definition=concept_blueprint_or_str)
            else:
                result[concept_code] = concept_blueprint_or_str
        return result

    @field_validator("concept", mode="after")
    def validate_refines_field(cls, value: Dict[str, ConceptBlueprint | str]) -> Dict[str, ConceptBlueprint | str]:
        for concept_code, concept_blueprint in value.items():
            if isinstance(concept_blueprint, str):
                continue

            if concept_blueprint.refines is None:
                continue

            ## Detect infinite refines loop
            if isinstance(concept_blueprint.refines, str) and concept_blueprint.refines == concept_code:
                raise ConceptBlueprintError(f"Forbidden refines field: '{concept_code}' refines itself.")
            elif isinstance(concept_blueprint.refines, list):
                for refine in concept_blueprint.refines:
                    if refine == concept_code:
                        raise ConceptBlueprintError(f"Forbidden refines field: '{concept_code}' refines itself.")
            else:
                raise ConceptBlueprintError(f"Forbidden refines field: '{concept_blueprint.refines}' is not a string or list.")

            # Validate refines field
            non_native_refines = ConceptBlueprint.extract_non_native_refines(concept_blueprint.refines)
            for refine in non_native_refines:
                if refine not in value.keys():
                    raise ConceptBlueprintError(
                        f"Refine '{refine}' in concept definition '{concept_code}' is not declared in the bundle and is not a native concept."
                    )
        return value
