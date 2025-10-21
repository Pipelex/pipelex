from typing import Any

from pipelex.client.protocol import PipelineResponse, PipelineState
from pipelex.core.memory.working_memory import MAIN_STUFF_NAME, DictWorkingMemory, WorkingMemory
from pipelex.core.pipes.pipe_output import DictPipeOutput, PipeOutput
from pipelex.core.stuffs.stuff import DictStuff


class PipelineResponseFactory:
    """Factory class for creating PipelineResponse objects from PipeOutput."""

    @staticmethod
    def _serialize_working_memory_with_dict_stuffs(working_memory: WorkingMemory) -> DictWorkingMemory:
        """Convert WorkingMemory to dict with DictStuff objects (content as dict).

        Keeps the WorkingMemory structure but converts each Stuff.content to dict.

        Args:
            working_memory: The WorkingMemory to serialize

        Returns:
            Dict with root containing DictStuff objects (serialized) and aliases
        """
        dict_stuffs_root: dict[str, DictStuff] = {}

        # Convert each Stuff → DictStuff by dumping only the content
        for stuff_name, stuff in working_memory.root.items():
            dict_stuff = DictStuff(
                concept=stuff.concept.concept_string,
                content=stuff.content.model_dump(serialize_as_any=True),
            )
            dict_stuffs_root[stuff_name] = dict_stuff

        return DictWorkingMemory(root=dict_stuffs_root, aliases=working_memory.aliases)

    @staticmethod
    def make_from_pipe_output(
        pipe_output: PipeOutput,
        status: str,
        pipeline_run_id: str = "",
        created_at: str = "",
        pipeline_state: PipelineState = PipelineState.COMPLETED,
        finished_at: str | None = None,
        message: str | None = None,
        error: str | None = None,
        pipe_structures: dict[str, Any] | None = None,
    ) -> PipelineResponse:
        """Create a PipelineResponse from a PipeOutput object.

        Args:
            pipe_output: The PipeOutput to convert
            pipeline_run_id: Unique identifier for the pipeline run
            created_at: Timestamp when the pipeline was created
            pipeline_state: Current state of the pipeline
            finished_at: Timestamp when the pipeline finished
            status: Status of the API call
            message: Optional message providing additional information
            error: Optional error message
            pipe_structures: Structure of the pipeline to execute
        Returns:
            PipelineResponse with the pipe output serialized to reduced format

        """
        return PipelineResponse(
            pipeline_run_id=pipeline_run_id,
            created_at=created_at,
            pipeline_state=pipeline_state,
            finished_at=finished_at,
            pipe_output=DictPipeOutput(
                working_memory=PipelineResponseFactory._serialize_working_memory_with_dict_stuffs(pipe_output.working_memory),
                pipeline_run_id=pipe_output.pipeline_run_id,
            ),
            pipe_structures=pipe_structures,
            main_stuff_name=pipe_output.working_memory.aliases.get(MAIN_STUFF_NAME, MAIN_STUFF_NAME),
            status=status,
            message=message,
            error=error,
        )

    @staticmethod
    def make_from_api_response(response: dict[str, Any]) -> PipelineResponse:
        """Create a PipelineResponse from an API response dictionary.

        Args:
            response: Dictionary containing the API response data

        Returns:
            PipelineResponse instance created from the response data

        """
        return PipelineResponse.model_validate(response)
