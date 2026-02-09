from typing import Any

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.tools.misc.json_utils import clean_json_content


class ApiSerializer:
    """Handles API-specific serialization with datetime formatting and cleanup."""

    @classmethod
    def serialize_working_memory_for_api(cls, working_memory: WorkingMemory | None = None) -> dict[str, dict[str, Any]]:
        """Convert WorkingMemory to API-ready format with proper datetime handling.

        Args:
            working_memory: The WorkingMemory to serialize

        Returns:
            PipelineInputs ready for API transmission with datetime strings and no __class__/__module__.
            Returns plain dicts with {"concept": str, "content": dict | list} structure for JSON serialization.

        """
        pipeline_inputs: dict[str, dict[str, Any]] = {}
        if working_memory is None:
            return pipeline_inputs

        for stuff_name, stuff in working_memory.root.items():
            content_dict = stuff.content.model_dump(serialize_as_any=True)
            clean_content = clean_json_content(content_dict)

            # Create plain dict instead of DictStuff instance for JSON serialization
            pipeline_inputs[stuff_name] = {
                "concept": stuff.concept.code,
                "content": clean_content,
            }

        return pipeline_inputs
