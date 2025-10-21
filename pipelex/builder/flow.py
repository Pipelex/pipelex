from pydantic import ConfigDict, Field, model_validator

from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.exceptions import PipelexException
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.tools.typing.validation_utils import has_exactly_one_among_attributes_from_list
from pipelex.types import Self


class FlowElementError(PipelexException):
    """Exception raised by FlowElement."""


# FlowElement as all possible pipe representations in a flow
class FlowElement(StructuredContent):
    operator_signature: PipeSignature | None = None
    controller_blueprint: PipeBatchBlueprint | PipeConditionBlueprint | PipeParallelBlueprint | PipeSequenceBlueprint | None = None

    @model_validator(mode="after")
    def validate_flow_element(self) -> Self:
        if not has_exactly_one_among_attributes_from_list(self, attributes_list=["operator_signature", "controller_blueprint"]):
            msg = "FlowElement must have exactly one of operator_signature or controller_blueprint"
            raise FlowElementError(msg)
        return self


class Flow(StructuredContent):
    """Simplified view of a pipeline's flow structure.

    This class provides a high-level overview of a pipeline's flow without
    implementation details. It shows:
    - Domain and description
    - Pipe controllers (sequence, parallel, condition, batch) with their full structure
    - Pipe operators (LLM, Func, ImgGgen, Compose, Extract) as signatures only

    This representation is useful for understanding the overall workflow and
    dependencies without getting into implementation specifics.

    Attributes:
        domain: The domain identifier for this pipeline in snake_case format.
        description: Natural language description of the pipeline's purpose.
        pipes: Dictionary mapping pipe codes to their specifications.
               Controllers include full details, operators are simplified to signatures.
    """

    model_config = ConfigDict(extra="forbid")

    domain: str
    description: str | None = None
    flow_elements: dict[str, FlowElement] = Field(default_factory=dict)
