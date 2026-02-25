from pydantic import ConfigDict, Field

from pipelex.cogt.content_generation.dry_run_factory import MockFormat
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.pipe_controllers.sub_pipe_blueprint import SubPipeBlueprint


class SubPipeSpec(StructuredContent):
    """Spec for a single step within a pipe controller.

    SubPipeSpec defines individual pipe executions within controller pipes
    (PipeSequence, PipeParallel, PipeBatch, PipeCondition).

    Attributes:
        pipe_code: The pipe code to execute. Must reference an existing pipe in the pipeline.
        result: Name to assign to the pipe's output in the context.

    Validation Rules:
        - pipe must reference a valid pipe code.
        - result, when specified, should follow naming conventions.

    """

    model_config = ConfigDict(extra="forbid")

    pipe_code: str = Field(json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    result: str = Field(json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    batch_over: str | None = Field(default=None, json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})
    batch_as: str | None = Field(default=None, json_schema_extra={"mock_format": MockFormat.SNAKE_CASE})

    def to_blueprint(self) -> SubPipeBlueprint:
        return SubPipeBlueprint(
            pipe=self.pipe_code,
            result=self.result,
            batch_over=self.batch_over,
            batch_as=self.batch_as,
        )
