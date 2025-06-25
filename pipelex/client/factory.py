from datetime import datetime
from typing import Any, Dict, List, Optional, cast

from kajson import kajson

from pipelex.client.protocol import PipelineRequest, PipelineResponse, PipelineState
from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.stuff_content import StuffContent
from pipelex.core.stuff_factory import StuffContentFactory, StuffFactory
from pipelex.core.working_memory import WorkingMemory
from pipelex.core.working_memory_factory import WorkingMemoryFactory


class ApiSerializationError(Exception):
    """Exception raised when API serialization fails."""

    pass


class ApiSerializer:
    """Handles API-specific serialization with kajson, datetime formatting, and cleanup."""

    # Fixed datetime format for API consistency
    API_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"

    @classmethod
    def serialize_working_memory_for_api(cls, working_memory: WorkingMemory) -> Dict[str, Dict[str, Any]]:
        """
        Convert WorkingMemory to API-ready format using kajson with proper datetime handling.

        Args:
            working_memory: The WorkingMemory to serialize

        Returns:
            Dict ready for API transmission with datetime strings and no __class__/__module__
        """
        reduced_memory: Dict[str, Dict[str, Any]] = {}

        for stuff_name, stuff in working_memory.root.items():
            if stuff.concept_code == NativeConcept.TEXT.code:
                # Handle text content directly
                item_dict: Dict[str, Any] = {
                    "concept_code": stuff.concept_code,
                    "content": stuff.content.text,  # type: ignore
                }
            else:
                # Use kajson for complex objects
                content_dict = stuff.content.model_dump(serialize_as_any=True)

                # Serialize with kajson and clean up
                content_json = kajson.dumps(content_dict)
                clean_content = kajson.loads(content_json)

                # Clean up API-unfriendly fields and fix datetime format
                clean_content = cls._clean_and_format_content(clean_content)

                item_dict = {
                    "concept_code": stuff.concept_code,
                    "content": clean_content,
                }

            reduced_memory[stuff_name] = item_dict

        return reduced_memory

    @classmethod
    def serialize_pipe_output_for_api(cls, pipe_output: PipeOutput) -> Dict[str, Dict[str, Any]]:
        """
        Convert PipeOutput to API-ready format.

        Args:
            pipe_output: The PipeOutput to serialize

        Returns:
            Dict ready for API transmission
        """
        return {"working_memory": cls.serialize_working_memory_for_api(pipe_output.working_memory)}

    @classmethod
    def _clean_and_format_content(cls, content: Any) -> Any:
        """
        Recursively clean content by removing __class__/__module__ and formatting datetimes.

        Args:
            content: Content to clean

        Returns:
            Cleaned content with formatted datetimes
        """
        if isinstance(content, dict):
            cleaned: Dict[str, Any] = {}
            content_dict = cast(Dict[str, Any], content)
            for key in content_dict:
                # Skip API-unfriendly fields
                if key in ("__class__", "__module__"):
                    continue
                cleaned[key] = cls._clean_and_format_content(content_dict[key])
            return cleaned
        elif isinstance(content, list):
            cleaned_list: List[Any] = []
            content_list = cast(List[Any], content)
            for idx in range(len(content_list)):
                cleaned_list.append(cls._clean_and_format_content(content_list[idx]))
            return cleaned_list
        elif isinstance(content, datetime):
            # Format datetime to fixed API format
            return content.strftime(cls.API_DATETIME_FORMAT)
        else:
            return content

    @classmethod
    def make_stuff_content_from_api_data(cls, concept_code: str, value: Dict[str, Any] | str) -> StuffContent:
        """
        Create StuffContent from API data using concept code.

        Args:
            concept_code: The concept code to determine the content type
            value: The content value from API

        Returns:
            StuffContent instance

        Raises:
            ApiSerializationError: If concept cannot be resolved or content creation fails
        """
        try:
            return StuffContentFactory.make_stuffcontent_from_concept_code_with_fallback(concept_code=concept_code, value=value)

        except Exception as e:
            raise ApiSerializationError(f"Failed to create StuffContent for concept '{concept_code}': {e}") from e


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
            reduced_memory = ApiSerializer.serialize_working_memory_for_api(working_memory)

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
            reduced_memory: Dictionary in the format from API

        Returns:
            WorkingMemory object reconstructed from the reduced format
        """
        working_memory = WorkingMemoryFactory.make_empty()
        if reduced_memory is None:
            return working_memory

        for stuff_key, stuff_data in reduced_memory.items():
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
            reduced_output = ApiSerializer.serialize_pipe_output_for_api(pipe_output)

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
