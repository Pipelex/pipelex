from typing import Any, Dict, Optional, Protocol, TypeVar

from pydantic import ConfigDict, model_validator
from typing_extensions import Self, runtime_checkable

from pipelex.core.concept_code_factory import ConceptCodeFactory
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
        if self.inputs:
            for input_name, input_concept_code in self.inputs.items():
                self.inputs[input_name] = ConceptCodeFactory.make_concept_code_from_str(
                    concept_str=input_concept_code,
                    fallback_domain=self.domain,
                )
        self.output = ConceptCodeFactory.make_concept_code_from_str(
            concept_str=self.output,
            fallback_domain=self.domain,
        )
        return self


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
