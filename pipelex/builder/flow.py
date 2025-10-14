from pydantic import ConfigDict, Field

from pipelex.builder.pipe.pipe_signature import PipeSignature
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_controllers.batch.pipe_batch_blueprint import PipeBatchBlueprint
from pipelex.pipe_controllers.condition.pipe_condition_blueprint import PipeConditionBlueprint
from pipelex.pipe_controllers.parallel.pipe_parallel_blueprint import PipeParallelBlueprint
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint

# Union of possible pipe representations in flow view
# Controllers keep their full blueprint, operators are converted to signatures
FlowElementUnion = PipeSignature | PipeBatchBlueprint | PipeConditionBlueprint | PipeParallelBlueprint | PipeSequenceBlueprint


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
    flow_elements: dict[str, FlowElementUnion] = Field(default_factory=dict)
