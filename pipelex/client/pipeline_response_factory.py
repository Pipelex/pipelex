from typing import Any, Dict, Optional

from pipelex.client.api_serializer import ApiSerializer
from pipelex.client.protocol import PipelineResponse, PipelineState
from pipelex.core.pipes.pipe_output import PipeOutput


class PipelineResponseFactory:
    """Factory class for creating PipelineResponse objects from PipeOutput."""

    @staticmethod
    def make_from_pipe_output(
        pipe_output: Optional[PipeOutput] = None,
        pipeline_run_id: str = "",
        created_at: str = "",
        pipeline_state: PipelineState = PipelineState.COMPLETED,
        finished_at: Optional[str] = None,
        status: Optional[str] = "success",
        message: Optional[str] = None,
        error: Optional[str] = None,
    ) -> PipelineResponse:
        """
        Create a PipelineResponse from a PipeOutput object.

        Args:
            pipe_output: The PipeOutput to convert
            pipeline_run_id: Unique identifier for the pipeline run
            created_at: Timestamp when the pipeline was created
            pipeline_state: Current state of the pipeline
            finished_at: Timestamp when the pipeline finished
            status: Status of the API call
            message: Optional message providing additional information
            error: Optional error message

        Returns:
            PipelineResponse with the pipe output serialized to reduced format
        """
        compact_output = None
        if pipe_output is not None:
            compact_output = ApiSerializer.serialize_pipe_output_for_api(pipe_output=pipe_output)

        return PipelineResponse(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            pipeline_state=pipeline_state,
            finished_at=finished_at,
            pipe_output=compact_output,
            status=status,
            message=message,
            error=error,
        )

    @staticmethod
    def make_from_api_response(response: Dict[str, Any]) -> PipelineResponse:
        """
        Create a PipelineResponse from an API response dictionary.

        Args:
            response: Dictionary containing the API response data

        Returns:
            PipelineResponse instance created from the response data
        """
        return PipelineResponse(**response)
