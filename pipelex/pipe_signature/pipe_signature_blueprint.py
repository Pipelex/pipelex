from typing import Literal

from pydantic import Field
from typing_extensions import override

from pipelex.core.pipes.pipe_blueprint import PipeBlueprint, PipeType


class PipeSignatureBlueprint(PipeBlueprint):
    """Contract-only pipe blueprint.

    A `PipeSignature` declares inputs and output but has no implementation. It exists so
    that an in-progress pipeline can be validated (dry-run mocks the declared output)
    before all its pipes are implemented.
    """

    type: Literal["PipeSignature"] = "PipeSignature"
    pipe_category: Literal["PipeSignature"] = "PipeSignature"
    signature_for: PipeType | None = Field(
        default=None,
        description="Intended downstream pipe type when this signature is implemented (optional hint for agents).",
    )
    signature_pipe_dependencies: list[str] = Field(
        default_factory=list,
        description="Pipes this signature claims to depend on (metadata for tooling).",
    )

    @override
    def validate_inputs(self) -> None:
        pass

    @override
    def validate_output(self) -> None:
        pass
