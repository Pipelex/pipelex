from abc import abstractmethod
from typing import Any, Protocol, Sequence

from pydantic import BaseModel, model_validator
from pydantic.functional_validators import SkipValidation
from typing_extensions import Annotated, runtime_checkable

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.pipe_output import DictPipeOutput
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.core.stuffs.stuff import DictStuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.exceptions import PipelexException
from pipelex.types import StrEnum

# StuffContentOrData represents all possible formats for pipeline inputs input:
# Case 1: Direct content (no 'concept' key)
#   - 1.1: str (simple string)
#   - 1.2: Sequence[str] (list of strings)
#   - 1.3: StuffContent (a StuffContent object)
#   - 1.4: Sequence[StuffContent] (list of StuffContent objects, covariant)
#   - 1.5: ListContent[StuffContent] (a ListContent object containing StuffContent items)
# Case 2: Dict with 'concept' AND 'content' keys
#   - 2.1: {"concept": str, "content": str}
#   - 2.2: {"concept": str, "content": Sequence[str]}
#   - 2.3: {"concept": str, "content": StuffContent}
#   - 2.4: {"concept": str, "content": Sequence[StuffContent]}
#   - 2.5: {"concept": str, "content": dict[str, Any]}
#   - 2.6: {"concept": str, "content": Sequence[dict[str, Any]}
#   Note: Case 2 formats can be provided as plain dict or DictStuff instance
StuffContentOrData = (
    str  # Case 1.1
    | Sequence[str]  # Case 1.2
    | StuffContent  # Case 1.3 (also covers Case 1.5 as ListContent is a StuffContent)
    | Sequence[StuffContent]  # Case 1.4 (covariant - accepts list[TextContent], etc.)
    | dict[str, Any]  # Case 2.1-2.7 - plain dicts with {"concept": str, "content": Any} structure
    | DictStuff  # Case 2.7 - DictStuff instances (same structure as dict but as Pydantic model)
)
PipelineInputs = dict[str, StuffContentOrData]  # Can include both dict and StuffContent


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
        status (str): Application-level status ("success", "error")
        message (str | None): Optional message providing additional information
        error (str | None): Optional error message when status is not "success"

    """

    status: str | None
    message: str | None = None
    error: str | None = None


class PipelineRequestError(PipelexException):
    pass


class PipelineRequest(BaseModel):
    """Request for executing a pipeline.

    Attributes:
        pipe_code (str | None): Code of the pipe to execute
        plx_content (str | None): Content of the pipeline bundle to execute
        inputs (PipelineInputs | None): Inputs in PipelineInputs format - Pydantic validation is skipped
            to preserve the flexible format (dicts, strings, StuffContent objects, etc.)
        output_name (str | None): Name of the output slot to write to
        output_multiplicity (PipeOutputMultiplicity | None): Output multiplicity setting
        dynamic_output_concept_code (str | None): Override for the dynamic output concept code

    """

    pipe_code: str | None = None
    plx_content: str | None = None
    inputs: Annotated[PipelineInputs | None, SkipValidation] = None
    output_name: str | None = None
    output_multiplicity: VariableMultiplicity | None = None
    dynamic_output_concept_code: str | None = None

    @model_validator(mode="before")
    @classmethod
    def validate_request(cls, values: dict[str, Any]):
        if values.get("pipe_code") is None and values.get("plx_content") is None:
            msg = (
                "pipe_code and plx_content cannot be None together. Its either: Both of them, or if there is no plx_content, "
                "then pipe_code must be provided and must reference a pipe already registered in the library."
                "If plx_content is provided but no pipe_code, plx_content must have a main_pipe property."
            )
            raise PipelineRequestError(msg)
        return values


class PipelineResponse(ApiResponse):
    """Response for pipeline execution requests.

    Attributes:
        pipeline_run_id (str): Unique identifier for the pipeline run
        created_at (str): Timestamp when the pipeline was created
        pipeline_state (PipelineState): Current state of the pipeline
        finished_at (str | None): Timestamp when the pipeline finished, if completed
        pipe_output (DictPipeOutput | None): Output data from the pipeline execution (working_memory dict + pipeline_run_id)
        main_stuff_name (str | None): Name of the main stuff in the pipeline output
        pipe_structures (dict[str, Any] | None): Structure of the pipeline to execute

    """

    pipeline_run_id: str
    created_at: str
    pipeline_state: PipelineState
    finished_at: str | None = None
    pipe_output: DictPipeOutput | None = None
    main_stuff_name: str | None = None
    pipe_structures: dict[str, Any] | None = None


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
        pipe_code: str | None = None,
        plx_content: str | None = None,
        inputs: PipelineInputs | WorkingMemory | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineResponse:
        """Execute a pipeline synchronously and wait for its completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            plx_content (str | None): Content of the pipeline bundle to execute
            inputs (PipelineInputs | WorkingMemory | None): Inputs passed to the pipeline
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
        pipe_code: str | None = None,
        plx_content: str | None = None,
        inputs: PipelineInputs | WorkingMemory | None = None,
        output_name: str | None = None,
        output_multiplicity: VariableMultiplicity | None = None,
        dynamic_output_concept_code: str | None = None,
    ) -> PipelineResponse:
        """Start a pipeline execution asynchronously without waiting for completion.

        Args:
            pipe_code (str): The code identifying the pipeline to execute
            plx_content (str | None): Content of the pipeline bundle to execute
            inputs (PipelineInputs | WorkingMemory | None): Inputs passed to the pipeline
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
