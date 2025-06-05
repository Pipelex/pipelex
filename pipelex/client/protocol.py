from abc import abstractmethod
from typing import Optional, Protocol

from pydantic import BaseModel
from typing_extensions import runtime_checkable

from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory
from pipelex.types import StrEnum


class PipelineState(StrEnum):
    """
    Enum representing the possible states of a pipe execution.
    """

    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"
    STARTED = "STARTED"


class ApiResponse(BaseModel):
    """
    Base response class for Pipelex API calls.

    Attributes:
        status (Optional[str]): Status of the API call ("success", "error", etc.)
        message (Optional[str]): Optional message providing additional information
        error (Optional[str]): Optional error message when status is not "success"
    """

    status: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None


class PipelineRequest(BaseModel):
    """
    Request for executing a pipeline.

    Attributes:
        working_memory (Optional[WorkingMemory]): WorkingMemory instance passed to the pipeline
        output_name (Optional[str]): Name of the output slot to write to
        output_multiplicity (Optional[PipeOutputMultiplicity]): Output multiplicity setting
        dynamic_output_concept_code (Optional[str]): Override for the dynamic output concept code
    """

    working_memory: Optional[WorkingMemory] = None
    output_name: Optional[str] = None
    output_multiplicity: Optional[PipeOutputMultiplicity] = None
    dynamic_output_concept_code: Optional[str] = None


class PipelineResponse(ApiResponse):
    """
    Response for pipeline execution requests.

    Attributes:
        pipeline_run_id (str): Unique identifier for the pipeline run
        created_at (str): Timestamp when the pipeline was created
        pipeline_state (PipelineState): Current state of the pipeline
        finished_at (Optional[str]): Timestamp when the pipeline finished, if completed
        pipe_output (Optional[PipeOutput]): Output data from the pipeline execution, if available
    """

    pipeline_run_id: str
    created_at: str
    pipeline_state: PipelineState
    finished_at: Optional[str] = None
    pipe_output: Optional[PipeOutput] = None


@runtime_checkable
class PipelexProtocol(Protocol):
    """
    Protocol defining the contract for the Pipelex API.

    This protocol specifies the interface that any Pipelex API implementation must adhere to.
    All methods are asynchronous and handle pipeline execution, monitoring, and control.

    Attributes:
        api_token (Optional[str]): Authentication token for API access
        api_base_url (Optional[str]): Base URL for the API
    """

    api_token: str
    api_base_url: str

    @abstractmethod
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipelineResponse:
        """
        Execute a pipeline synchronously and wait for its completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            working_memory (Optional[WorkingMemory]): Memory context passed to the pipeline
            output_name (Optional[str]): Target output slot name
            output_multiplicity (Optional[PipeOutputMultiplicity]): Output multiplicity setting
            dynamic_output_concept_code (Optional[str]): Override for dynamic output concept
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
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipelineResponse:
        """
        Start a pipeline execution asynchronously without waiting for completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            working_memory (Optional[WorkingMemory]): Memory context passed to the pipeline
            output_name (Optional[str]): Target output slot name
            output_multiplicity (Optional[PipeOutputMultiplicity]): Output multiplicity setting
            dynamic_output_concept_code (Optional[str]): Override for dynamic output concept

        Returns:
            PipelineResponse: Initial response with pipeline_run_id and created_at timestamp

        Raises:
            HTTPException: On pipeline start failure
            ClientAuthenticationError: If API token is missing for API execution
        """
        ...
