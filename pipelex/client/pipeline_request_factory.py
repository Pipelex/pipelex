from typing import Any, cast

from pipelex.client.api_serializer import ApiSerializer
from pipelex.client.protocol import PipelineInputs, PipelineRequest
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


class PipelineRequestFactory:
    """Factory class for creating PipelineRequest objects from WorkingMemory."""

    @staticmethod
    def make_from_working_memory(
        pipe_code: str | None,
        plx_content: str | None,
        working_memory: WorkingMemory | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineRequest:
        """Create a PipelineRequest from a WorkingMemory object.

        Args:
            pipe_code: The code identifying the pipeline to execute
            plx_content: Content of the pipeline bundle to execute
            working_memory: The WorkingMemory to convert
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for the dynamic output concept code
            plx_content: Content of the pipeline bundle to execute
        Returns:
            PipelineRequest with the working memory serialized to reduced format

        """
        return PipelineRequest(
            pipe_code=pipe_code,
            plx_content=plx_content,
            # `ApiSerializer.serialize_working_memory_for_api` returns a dict[str, dict[str, Any]] (plain dicts), which is a valid PipelineInputs
            inputs=cast("PipelineInputs", ApiSerializer.serialize_working_memory_for_api(working_memory=working_memory)),
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @staticmethod
    def make_from_body(request_body: dict[str, Any]) -> PipelineRequest:
        """Create a PipelineRequest from raw request body dictionary.

        Args:
            request_body: Raw dictionary from API request body

        Returns:
            PipelineRequest object with dictionary working_memory

        """
        return PipelineRequest(
            pipe_code=request_body.get("pipe_code"),
            plx_content=request_body.get("plx_content"),
            inputs=request_body.get("inputs", {}),
            output_name=request_body.get("output_name"),
            output_multiplicity=request_body.get("output_multiplicity"),
            dynamic_output_concept_code=request_body.get("dynamic_output_concept_code"),
        )
