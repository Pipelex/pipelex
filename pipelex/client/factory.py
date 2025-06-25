from typing import Any, Dict, Optional

from pipelex.client.protocol import PipelineRequest, PipelineResponse, PipelineState
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuff_factory import StuffBlueprint, StuffFactory
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
        reduced_memory = None
        if working_memory is not None:
            reduced_memory = working_memory.to_reduced_memory()

        return PipelineRequest(
            working_memory=reduced_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @staticmethod
    def make_working_memory_from_reduced(reduced_memory: Optional[Dict[str, Dict[str, Any]]]) -> WorkingMemory:
        """
        Create a WorkingMemory from a reduced memory dictionary.

        Args:
            reduced_memory: Dictionary in the format of WorkingMemory.to_reduced_memory()

        Returns:
            WorkingMemory object reconstructed from the reduced format
        """
        working_memory = WorkingMemoryFactory.make_empty()
        if reduced_memory is None:
            return working_memory

        for stuff_key, stuff_data in reduced_memory.items():
            blueprint = StuffBlueprint(stuff_name=stuff_key, concept_code=stuff_data.get("concept_code", ""), content=stuff_data.get("content", {}))
            working_memory.add_new_stuff(name=stuff_key, stuff=StuffFactory.make_from_blueprint(blueprint=blueprint))
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
            working_memory=request_body.get("working_memory"),
            output_name=request_body.get("output_name"),
            output_multiplicity=request_body.get("output_multiplicity"),
            dynamic_output_concept_code=request_body.get("dynamic_output_concept_code"),
        )


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
        reduced_output = None
        if pipe_output is not None:
            reduced_output = pipe_output.to_reduced_memory()

        return PipelineResponse(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            pipeline_state=pipeline_state,
            finished_at=finished_at,
            pipe_output=reduced_output,
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
