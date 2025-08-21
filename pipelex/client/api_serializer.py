from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from pipelex.client.protocol import CompactMemory
from pipelex.core.concepts.concept_native import NativeConceptEnum
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.stuff_content import TextContent


class ApiSerializer:
    """Handles API-specific serialization with kajson, datetime formatting, and cleanup."""

    # Fixed datetime format for API consistency
    API_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
    FIELDS_TO_SKIP = ("__class__", "__module__")

    @classmethod
    def serialize_working_memory_for_api(cls, working_memory: Optional[WorkingMemory] = None) -> CompactMemory:
        """
        Convert WorkingMemory to API-ready format using kajson with proper datetime handling.

        Args:
            working_memory: The WorkingMemory to serialize

        Returns:
            Dict ready for API transmission with datetime strings and no __class__/__module__
        """
        compact_memory: CompactMemory = {}
        if working_memory is None:
            return compact_memory

        for stuff_name, stuff in working_memory.root.items():
            if stuff.concept.code == NativeConceptEnum.TEXT.value:
                stuff_content = cast(TextContent, stuff.content)
                item_dict: Dict[str, Any] = {
                    "concept_code": stuff.concept.code,
                    "content": stuff_content.text,
                }
            else:
                content_dict = stuff.content.model_dump(serialize_as_any=True)
                clean_content = cls._clean_and_format_content(content_dict)

                item_dict = {
                    "concept_code": stuff.concept.code,
                    "content": clean_content,
                }

            compact_memory[stuff_name] = item_dict

        return compact_memory

    @classmethod
    def serialize_pipe_output_for_api(cls, pipe_output: PipeOutput) -> CompactMemory:
        """
        Convert PipeOutput to API-ready format.

        Args:
            pipe_output: The PipeOutput to serialize

        Returns:
            Dict ready for API transmission
        """
        return {"compact_memory": cls.serialize_working_memory_for_api(pipe_output.working_memory)}

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
        elif isinstance(content, Enum):
            return content.value  # Convert enum to its value
        elif isinstance(content, Decimal):
            return float(content)  # Convert Decimal to float for JSON compatibility
        elif isinstance(content, Path):
            return str(content)  # Convert Path to string representation
        else:
            return content
