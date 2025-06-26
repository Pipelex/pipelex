from datetime import datetime
from typing import Any, Dict, List, cast

from kajson import kajson

from pipelex.core.concept_native import NativeConcept
from pipelex.core.pipe_output import PipeOutput
from pipelex.core.stuff_content import StuffContent, TextContent
from pipelex.core.stuff_factory import StuffContentFactory
from pipelex.core.working_memory import WorkingMemory


class ApiSerializationError(Exception):
    """Exception raised when API serialization fails."""

    pass


class ApiSerializer:
    """Handles API-specific serialization with kajson, datetime formatting, and cleanup."""

    # Fixed datetime format for API consistency
    API_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
    FIELDS_TO_SKIP = ("__class__", "__module__")

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
                stuff_content = cast(TextContent, stuff.content)
                item_dict: Dict[str, Any] = {
                    "concept_code": stuff.concept_code,
                    "content": stuff_content.text,
                }
            else:
                content_dict = stuff.content.model_dump(serialize_as_any=True)

                content_json = kajson.dumps(content_dict)
                clean_content = kajson.loads(content_json)

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
        Recursively clean content by removing the fields in FIELDS_TO_SKIP and formatting datetimes.

        Args:
            content: Content to clean

        Returns:
            Cleaned content with formatted datetimes
        """
        if isinstance(content, dict):
            cleaned: Dict[str, Any] = {}
            content_dict = cast(Dict[str, Any], content)
            for key in content_dict:
                if key in cls.FIELDS_TO_SKIP:
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
