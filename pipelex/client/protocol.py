from abc import abstractmethod
from typing import Optional, Protocol

from pydantic import BaseModel, Field
from typing_extensions import runtime_checkable

from pipelex.core.pipe_output import PipeOutput
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory
from pipelex.types import StrEnum


class PipeState(StrEnum):
    """
    Enum representing the possible states of a pipe execution.
    """

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ApiResponse(BaseModel):
    """
    Base response class for Pipelex API calls.

    Attributes:
        status: Status of the API call ("success", "error", etc.)
        message: Optional message providing additional information
        error: Optional error message when status is not "success"
    """

    status: str
    message: Optional[str] = None
    error: Optional[str] = None


class PipeStatus(BaseModel):
    """
    Status information for a pipe execution.

    Attributes:
        pipe_execution_id: Unique identifier for this execution
        pipe_code: Code of the pipe that was executed
        state: Current state of execution (running, completed, failed, etc.)
        created_at: ISO 8601 formatted timestamp (YYYY-MM-DDThh:mm:ss.sssZ) when execution started
        finished_at: ISO 8601 formatted timestamp (YYYY-MM-DDThh:mm:ss.sssZ) when execution finished,
                     only populated for completed or failed executions
        result: Complete WorkingMemory with all results, only populated when execution is finished
        main_output: Primary output Stuff instance, only populated when execution is finished
    """

    pipe_execution_id: str
    pipe_code: str
    state: PipeState
    created_at: Optional[str] = None  # ISO format timestamp, only populated when execution is finished
    finished_at: Optional[str] = None  # ISO format timestamp, only populated when execution is finished
    pipe_output: Optional[PipeOutput] = None


class PipeStartResponse(ApiResponse):
    """
    Response for pipe execution requests when starting a pipe in non-blocking mode.

    This response is returned when a pipe execution is started but does not wait for completion.
    It contains only the minimal details needed to identify and track the execution.
    For results, the client must call get_pipe_status with the pipe_execution_id.

    Attributes:
        pipe_execution_id: Unique identifier for this execution, used to check status later
        created_at: ISO 8601 formatted timestamp (YYYY-MM-DDThh:mm:ss.sssZ) when execution started

        # Inherited from ApiResponse:
        status: Status of the API call ("success", "error", etc.)
        message: Optional message providing additional information
        error: Optional error message when status is not "success"
    """

    pipe_execution_id: str
    created_at: str


class PipeRequest(BaseModel):
    """
    Request model for executing a pipe.
    """

    memory: WorkingMemory = Field(..., description="Input memory for the pipe")
    dynamic_output_concept: Optional[str] = Field(default=None, description="Concept code of the output stuff")
    output_multiplicity: Optional[PipeOutputMultiplicity] = Field(default=None, description="Multiplicity of the output stuff")


@runtime_checkable
class PipelexProtocol(Protocol):
    """
    Protocol defining the contract for the Pipelex API.

    This protocol specifies the interface that any Pipelex API implementation must adhere to.
    The protocol includes methods for executing pipes both synchronously and asynchronously,
    as well as cancelling running executions.
    """

    @abstractmethod
    async def execute_pipe(self, pipe_code: str, request: PipeRequest) -> PipeStatus:
        """
        Execute a pipe with the given memory and wait for completion.

        This is a blocking operation that does not return until the pipe execution
        is complete. For long-running pipes, consider using start_pipe instead.

        Args:
            pipe_code: The unique identifier for the pipe to execute
            request: PipeRequest containing the input instances required by the pipe

        Returns:
            PipeStatus with the final execution status including complete results.

        Raises:
            HTTPException: If the execution fails or encounters an error
        """
        ...

    @abstractmethod
    async def start_pipe(self, pipe_code: str, request: PipeRequest) -> PipeStartResponse:
        """
        Start a pipe execution in the background without waiting for completion.

        This is a non-blocking operation that returns immediately with an execution ID.

        Args:
            pipe_code: The unique identifier for the pipe to execute
            request: PipeRequest containing the input instances required by the pipe

        Returns:
            PipeStartResponse with the pipe_execution_id and created_at timestamp.

        Raises:
            HTTPException: If starting the execution fails
        """
        ...

    @abstractmethod
    async def cancel_pipe(self, pipe_execution_id: str) -> ApiResponse:
        """
        Cancel a running pipe execution.

        This method allows clients to stop a pipe execution that is currently in progress.
        Once cancelled, a pipe cannot be resumed and must be started again if needed.

        Args:
            pipe_execution_id: The unique identifier for the pipe execution

        Returns:
            ApiResponse indicating success or failure of the cancellation

        Raises:
            HTTPException: If the cancellation fails or the execution ID is invalid
        """
        ...

    @abstractmethod
    async def get_pipe_status(self, pipe_execution_id: str) -> PipeStatus:
        """
        Get the current status of a pipe execution.

        This method allows clients to check the current status of a pipe execution
        that was started with start_pipe.

        Args:
            pipe_execution_id: The unique identifier for the pipe execution

        Returns:
            PipeStatus with the current execution status

        Raises:
            HTTPException: If the status check fails or the execution ID is invalid
        """
        ...
