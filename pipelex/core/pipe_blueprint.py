from typing import Any, Dict, Optional, Protocol, TypeVar

from pydantic import ConfigDict, field_validator, model_validator
from typing_extensions import Self, runtime_checkable

from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_abstract import PipeAbstract
from pipelex.core.stuff_content import StructuredContent


class PipeBlueprint(StructuredContent):
    model_config = ConfigDict(extra="forbid")

    definition: Optional[str] = None
    inputs: Optional[Dict[str, str]] = None
    output: str
    domain: str

    @model_validator(mode="after")
    def add_domain_prefix(self) -> Self:
        # if self.input and "." not in self.input:
        #     self.input = f"{self.domain}.{self.input}"
        if self.inputs:
            for input_name, input_concept_code in self.inputs.items():
                if "." not in input_concept_code:
                    self.inputs[input_name] = f"{self.domain}.{input_concept_code}"
        if self.output and "." not in self.output:
            self.output = f"{self.domain}.{self.output}"
        return self

    @classmethod
    def _add_native_prefix_if_needed(cls, value: str) -> str:
        if value in NativeConcept.names():
            return f"native.{value}"
        return value

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, value: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if value:
            return {name: cls._add_native_prefix_if_needed(concept_code) for name, concept_code in value.items()}
        return value

    @field_validator("output")
    @classmethod
    def validate_output(cls, value: str) -> str:
        return cls._add_native_prefix_if_needed(value)


PipeBlueprintType = TypeVar("PipeBlueprintType", bound="PipeBlueprint", contravariant=True)

PipeType = TypeVar("PipeType", bound="PipeAbstract", covariant=True)


@runtime_checkable
class PipeSpecificFactoryProtocol(Protocol[PipeBlueprintType, PipeType]):
    @classmethod
    def make_pipe_from_blueprint(
        cls,
        domain_code: str,
        pipe_code: str,
        pipe_blueprint: PipeBlueprintType,
    ) -> PipeType: ...

    @classmethod
    def make_pipe_from_details_dict(
        cls,
        domain_code: str,
        pipe_code: str,
        details_dict: Dict[str, Any],
    ) -> PipeType: ...
