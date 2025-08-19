from typing import Any, Dict, Optional, Protocol, TypeVar

from pydantic import BaseModel
from typing_extensions import runtime_checkable

from pipelex.core.pipe.pipe_abstract import PipeAbstract


class PipeBlueprint(BaseModel):
    type: str
    definition: Optional[str] = None
    inputs: Optional[Dict[str, str]] = None
    output: str


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
