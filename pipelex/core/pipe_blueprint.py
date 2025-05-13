# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict, Optional, Protocol, TypeVar

from pydantic import ConfigDict, field_validator, model_validator
from typing_extensions import Self, runtime_checkable

from pipelex.core.concept_native import NativeConceptCode
from pipelex.core.pipe import PipeAbstract
from pipelex.core.stuff_content import StructuredContent


class PipeBlueprint(StructuredContent):
    model_config = ConfigDict(extra="forbid")

    definition: Optional[str] = None
    input: Optional[str] = None
    output: str
    domain: str

    @model_validator(mode="after")
    def add_domain_prefix(self) -> Self:
        if self.input and "." not in self.input:
            self.input = f"{self.domain}.{self.input}"
        if self.output and "." not in self.output:
            self.output = f"{self.domain}.{self.output}"
        return self

    @classmethod
    def _add_native_prefix_if_needed(cls, value: str) -> str:
        if value in list(NativeConceptCode):
            return f"native.{value}"
        return value

    @field_validator("input")
    @classmethod
    def validate_input(cls, value: Optional[str]) -> Optional[str]:
        if value:
            return cls._add_native_prefix_if_needed(value)
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
