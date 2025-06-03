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


@runtime_checkable
class PipelexProtocol(Protocol):
    """
    Protocol defining the contract for the Pipelex API.

    This protocol specifies the interface that any Pipelex API implementation must adhere to.
    The protocol includes methods for executing pipelines both synchronously and asynchronously,
    as well as cancelling running executions.
    """

    api_token: Optional[str] = None

    @abstractmethod
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipeStatus:
        """
        Execute a pipeline and wait for its completion.

        This is a blocking operation that does not return until the pipeline execution
        is complete. For long-running pipelines, consider using start_pipeline instead.

        Args:
            pipe_code: The code of the pipeline to execute
            working_memory: Optional WorkingMemory instance passed to the pipeline
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity
            dynamic_output_concept_code: Override the dynamic output concept code

        Returns:
            PipeStatus with the final execution status including complete results.

        Raises:
            HTTPException: If the execution fails or encounters an error
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
    ) -> PipeStartResponse:
        """
        Start a pipeline execution in the background without waiting for completion.

        This is a non-blocking operation that returns immediately with an execution ID.

        Args:
            pipe_code: The code of the pipeline to execute
            working_memory: Optional WorkingMemory instance passed to the pipeline
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity
            dynamic_output_concept_code: Override the dynamic output concept code

        Returns:
            PipeStartResponse with the pipe_execution_id and created_at timestamp.

        Raises:
            HTTPException: If starting the execution fails
        """
        ...

    @abstractmethod
    async def cancel_pipeline(self, pipeline_run_id: str) -> ApiResponse:
        """
        Cancel a running pipeline execution.

        This method allows clients to stop a pipeline execution that is currently in progress.
        Once cancelled, a pipeline cannot be resumed and must be started again if needed.

        Args:
            pipeline_run_id: The unique identifier for the pipeline execution

        Returns:
            ApiResponse indicating success or failure of the cancellation

        Raises:
            HTTPException: If the cancellation fails or the execution ID is invalid
        """
        ...

    @abstractmethod
    async def get_pipeline_status(self, pipeline_run_id: str) -> PipeStatus:
        """
        Get the current status of a pipeline execution.

        This method allows clients to check the current status of a pipeline execution
        that was started with start_pipeline.

        Args:
            pipeline_run_id: The unique identifier for the pipeline execution

        Returns:
            PipeStatus with the current execution status

        Raises:
            HTTPException: If the status check fails or the execution ID is invalid
        """
        ...
