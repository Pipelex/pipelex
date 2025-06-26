from typing import Any, Dict, Optional

from pipelex.client.api_serializer import ApiSerializer
from pipelex.client.protocol import COMPACT_MEMORY_KEY, CompactMemory, PipelineRequest
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuff_factory import StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory


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
        compact_memory = None
        if working_memory is not None:
            compact_memory = ApiSerializer.serialize_working_memory_for_api(working_memory)

        return PipelineRequest(
            compact_memory=compact_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @staticmethod
    def make_working_memory_from_reduced(compact_memory: Optional[CompactMemory]) -> WorkingMemory:
        """
        Create a WorkingMemory from a reduced memory dictionary.

        Args:
            compact_memory: Dictionary in the format from API

        Returns:
            WorkingMemory object reconstructed from the reduced format
        """
        working_memory = WorkingMemoryFactory.make_empty()
        if compact_memory is None:
            return working_memory

        for stuff_key, stuff_data in compact_memory.items():
            concept_code = stuff_data.get("concept_code", "")
            content_value = stuff_data.get("content", {})

            # Use API serializer to create content
            content = ApiSerializer.make_stuff_content_from_api_data(concept_code=concept_code, value=content_value)

            # Create stuff directly
            stuff = StuffFactory.make_stuff(concept_str=concept_code, name=stuff_key, content=content)

            working_memory.add_new_stuff(name=stuff_key, stuff=stuff)

        return working_memory

    @staticmethod
    def make_request_from_body(request_body: Dict[str, Any]) -> PipelineRequest:
        """
        Create a PipelineRequest from raw request body dictionary.

        Args:
            request_body: Raw dictionary from API request body

        Returns:
            PipelineRequest object with dictionary working_memory
        """
        return PipelineRequest(
            compact_memory=request_body.get(COMPACT_MEMORY_KEY),
            output_name=request_body.get("output_name"),
            output_multiplicity=request_body.get("output_multiplicity"),
            dynamic_output_concept_code=request_body.get("dynamic_output_concept_code"),
        )
