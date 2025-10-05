from abc import abstractmethod
from typing import Any, Protocol

from pydantic import BaseModel
from typing_extensions import runtime_checkable

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.pipe_run.pipe_run_params import PipeOutputMultiplicity
from pipelex.types import StrEnum

StuffContentOrData = dict[str, Any] | StuffContent | list[Any] | str
ImplicitMemory = dict[str, StuffContentOrData]
CompactMemory = dict[str, dict[str, Any]]
COMPACT_MEMORY_KEY = "compact_memory"


class PipelineState(StrEnum):
    """Enum representing the possible states of a pipe execution."""

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    STARTED = "STARTED"


class ApiResponse(BaseModel):
    """Base response class for Pipelex API calls.

    Attributes:
        status (str | None): Status of the API call ("success", "error", etc.)
        message (str | None): Optional message providing additional information
        error (str | None): Optional error message when status is not "success"

    """

    status: str | None = None
    message: str | None = None
    error: str | None = None


class PipelineRequest(BaseModel):
    """Request for executing a pipeline.

    Attributes:
        input_memory (CompactMemory | None): In the format of WorkingMemory.to_compact_memory()
        output_name (str | None): Name of the output slot to write to
        output_multiplicity (PipeOutputMultiplicity | None): Output multiplicity setting
        dynamic_output_concept_code (str | None): Override for the dynamic output concept code

    """

    input_memory: CompactMemory | None = None
    output_name: str | None = None
    output_multiplicity: PipeOutputMultiplicity | None = None
    dynamic_output_concept_code: str | None = None


class PipelineResponse(ApiResponse):
    """Response for pipeline execution requests.

    Attributes:
        pipeline_run_id (str): Unique identifier for the pipeline run
        created_at (str): Timestamp when the pipeline was created
        pipeline_state (PipelineState): Current state of the pipeline
        finished_at (str | None): Timestamp when the pipeline finished, if completed
        pipe_output (CompactMemory | None): Output data from the pipeline execution as raw dict, if available

        Example of pipe_output:
        "pipe_output": {
            "input_memory": {
                "text": {
                    "concept_code": "native.Text",
                    "content": "Some text........"
                },
                "question": {
                    "concept_code": "answer.Question",
                    "content": {
                        "text": "What are aerodynamic features?"
                    }
                },
                "main_stuff": {
                    "concept_code": "retrieve.RetrievedExcerpt",
                    "content": {
                        "items": [
                            {
                                "text": "What we're seeing isn't just an incremental...",
                                "justification": "This excerpt directly mentions the 'aerodynamic profile' of ...."
                            },
                            ...
                        ]
                    }
                }
            }
        }

    """

    pipeline_run_id: str
    created_at: str
    pipeline_state: PipelineState
    finished_at: str | None = None
    pipe_output: CompactMemory | None = None


@runtime_checkable
class PipelexProtocol(Protocol):
    """Protocol defining the contract for the Pipelex API.

    This protocol specifies the interface that any Pipelex API implementation must adhere to.
    All methods are asynchronous and handle pipeline execution, monitoring, and control.

    Attributes:
        api_token (str): Authentication token for API access
        api_base_url (str): Base URL for the API

    """

    api_token: str
    api_base_url: str

    @abstractmethod
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: WorkingMemory | None = None,
        input_memory: CompactMemory | None = None,
        output_name: str | None = None,
        output_multiplicity: PipeOutputMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineResponse:
        """Execute a pipeline synchronously and wait for its completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            working_memory (WorkingMemory | None): Memory context passed to the pipeline
            input_memory (CompactMemory | None): Input memory passed to the pipeline
            output_name (str | None): Target output slot name
            output_multiplicity (PipeOutputMultiplicity | None): Output multiplicity setting
            dynamic_output_concept_code (str | None): Override for dynamic output concept
        Returns:
            PipelineResponse: Complete execution results including pipeline state and output

        Raises:
            HTTPException: On execution failure or error
            ClientAuthenticationError: If API token is missing for API execution

        """
        ...

    @abstractmethod
    async def start_pipeline(
        self,
        pipe_code: str,
        working_memory: WorkingMemory | None = None,
        input_memory: CompactMemory | None = None,
        output_name: str | None = None,
        output_multiplicity: PipeOutputMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineResponse:
        """Start a pipeline execution asynchronously without waiting for completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            working_memory (WorkingMemory | None): Memory context passed to the pipeline
            input_memory (CompactMemory | None): Input memory passed to the pipeline
            output_name (str | None): Target output slot name
            output_multiplicity (PipeOutputMultiplicity | None): Output multiplicity setting
            dynamic_output_concept_code (str | None): Override for dynamic output concept

        Returns:
            PipelineResponse: Initial response with pipeline_run_id and created_at timestamp

        Raises:
            HTTPException: On pipeline start failure
            ClientAuthenticationError: If API token is missing for API execution

        """
        ...
