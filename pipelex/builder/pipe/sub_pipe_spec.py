from pydantic import ConfigDict, model_validator

from pipelex.core.pipe_errors import PipeDefinitionError
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint
from pipelex.types import Self


class SubPipeSpec(StructuredContent):
    """Spec for a single step within a pipe controller.

    SubPipeSpec defines individual pipe executions within controller pipes
    (PipeSequence, PipeParallel, PipeBatch, PipeCondition). Supports output
    cardinality control and batch processing configuration.

    Attributes:
        pipe_code: The pipe code to execute. Must reference an existing pipe in the pipeline.
        result: Name to assign to the pipe's output in the context.
        batch_over: Name of the list in context to iterate over for batch processing.
                   When false (default), no batching occurs. When specified as string,
                   references a list in context. Requires batch_as when set.
        batch_as: Name to assign to the current item during batch iteration.
                 Required when batch_over is specified.

    Validation Rules:
        2. batch_over and batch_as must be specified together (both or neither).
        3. pipe must reference a valid pipe code.
        4. result, when specified, should follow naming conventions.

    """

    model_config = ConfigDict(extra="forbid")

    pipe_code: str
    result: str
    batch_over: str | None = None
    batch_as: str | None = None

    @model_validator(mode="after")
    def validate_batch_params(self) -> Self:
        if self.batch_over and not self.batch_as:
            msg = f"In pipe '{self.pipe_code}': When 'batch_over' is specified, 'batch_as' must also be provided"
            raise PipeDefinitionError(msg)

        if self.batch_as and not self.batch_over:
            msg = f"In pipe '{self.pipe_code}': When 'batch_as' is specified, 'batch_over' must also be provided"
            raise PipeDefinitionError(msg)

        return self

    def to_blueprint(self) -> SubPipeBlueprint:
        return SubPipeBlueprint(
            pipe=self.pipe_code,
            result=self.result,
            batch_over=self.batch_over,
            batch_as=self.batch_as,
        )
