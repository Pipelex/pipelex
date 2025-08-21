from typing import Any, Dict, Optional

from pipelex.client.api_serializer import ApiSerializer
from pipelex.client.protocol import COMPACT_MEMORY_KEY, PipelineRequest
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity


class PipelineRequestFactory:
    """Factory class for creating PipelineRequest objects from WorkingMemory."""

    @staticmethod
    def make_from_working_memory(
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipelineRequest:
        """
        Create a PipelineRequest from a WorkingMemory object.

        Args:
            working_memory: The WorkingMemory to convert
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for the dynamic output concept code

        Returns:
            PipelineRequest with the working memory serialized to reduced format
        """

        return PipelineRequest(
            input_memory=ApiSerializer.serialize_working_memory_for_api(working_memory),
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @staticmethod
    def make_from_body(request_body: Dict[str, Any]) -> PipelineRequest:
        """
        Create a PipelineRequest from raw request body dictionary.

        Args:
            request_body: Raw dictionary from API request body

        Returns:
            PipelineRequest object with dictionary working_memory
        """
        return PipelineRequest(
            input_memory=request_body.get(COMPACT_MEMORY_KEY),
            output_name=request_body.get("output_name"),
            output_multiplicity=request_body.get("output_multiplicity"),
            dynamic_output_concept_code=request_body.get("dynamic_output_concept_code"),
        )
