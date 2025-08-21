import re
from typing import Annotated, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint, ConceptBlueprintError
from pipelex.core.domains.domain import DomainError
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
        if not re.match(r"^[a-z][a-z0-9_]*$", domain):
            raise DomainError(f"Domain must be snake_case (lowercase letters, numbers, and underscores only) for domain '{domain}': {domain}")
        return domain

    @model_validator(mode="after")
    def validate_pipe(self) -> Self:
        # Validate the concept codes in the pipe inputs blueprint.
        if self.pipe is None:
            return self

        for pipe_code, pipe_blueprint in self.pipe.items():
            if pipe_blueprint.inputs is not None:
                for _, input_requirement_blueprint in pipe_blueprint.inputs.items():
                    Concept.validate_concept_string(input_requirement_blueprint.concept_code)
                    if self.concept:
                        if "." not in input_requirement_blueprint.concept_code and not Concept.is_native_concept_code(
                            input_requirement_blueprint.concept_code
                        ):
                            if input_requirement_blueprint.concept_code not in self.concept.keys():
                                raise ConceptBlueprintError(
                                    f"Concept '{input_requirement_blueprint.concept_code}' in pipe '{pipe_code}' is not declared in the bundle."
                                )
        return self

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
            if isinstance(concept_blueprint.refines, str):
                if concept_blueprint.refines == concept_code:
                    raise ConceptBlueprintError(f"Forbidden refines field: '{concept_code}' refines itself.")
            else:
                for refine in concept_blueprint.refines:
                    if refine == concept_code:
                        raise ConceptBlueprintError(f"Forbidden refines field: '{concept_code}' refines itself.")

            # Validate refines field
            non_native_refines = ConceptBlueprint.extract_non_native_refines(concept_blueprint.refines)
            for refine in non_native_refines:
                if refine not in value.keys():
                    raise ConceptBlueprintError(
                        f"Refine '{refine}' in concept definition '{concept_code}' is not declared in the bundle and is not a native concept."
                        "Either this concept does not exist or it is not declared in the bundle and so you need to add the corresponding domain."
                    )
        return value
