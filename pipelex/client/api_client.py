from typing import Any, Optional, cast

import httpx
from kajson import kajson
from typing_extensions import override

from pipelex.client.protocol import ApiResponse, PipelexProtocol, PipelineRequest, PipeStartResponse, PipeStatus
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory
from pipelex.tools.environment import get_required_env


class PipelexApiClient(PipelexProtocol):
    """
    API client for interacting with the Pipelex API.
    """

    def __init__(self, api_token: str):
        self.api_token = api_token
        self.api_base_url = get_required_env("PIPELEX_API_BASE_URL")

    def start_client(self) -> "PipelexApiClient":
        self.client = httpx.AsyncClient(base_url=self.api_base_url, headers={"Authorization": f"Bearer {self.api_token}"})
        return self

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def _make_api_call(self, endpoint: str, request: Optional[str] = None) -> Any:
        """Make an API call to the Pipelex server.
        Args:
            endpoint: The API endpoint to call, relative to the base URL
            request: A JSON-formatted string to send as the request body, or None if no body is needed
        Returns:
            Any: The JSON-decoded response from the server
        Raises:
            httpx.HTTPError: If the request fails or returns a non-200 status code
        """
        # Convert JSON string to UTF-8 bytes if not None
        content = request.encode("utf-8") if request is not None else None
        response = await self.client.post(f"/{endpoint}", content=content, headers={"Content-Type": "application/json"}, timeout=1200)
        response.raise_for_status()
        return response.json()

    @override
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipeStatus:
        """
        Execute a pipe with the given request and wait for completion.
        This is a blocking operation that does not return until the pipe execution
        is complete. For long-running pipes, consider using start_pipe instead.
        Args:
            pipe_code: The unique identifier for the pipe to execute
            request: PipeRequest containing memory and output concept
        Returns:
            PipeStatus with the final execution status and pipe output
        Raises:
            HTTPException: If the request fails or returns a non-200 status code
        """
        pipeline_request = PipelineRequest(
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call(f"pipelex/v1/pipes/{pipe_code}/execute", request=kajson.dumps(pipeline_request))
        return cast(PipeStatus, kajson.loads(response))
        # raise NotImplementedError("Pipelex API functionality is coming soon!")

    @override
    async def start_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipeStartResponse:
        raise NotImplementedError("Pipelex API functionality is coming soon!")

    @override
    async def cancel_pipeline(
        self,
        pipeline_run_id: str,
    ) -> ApiResponse:
        """
        Cancel a running pipe execution.
        This method attempts to cancel a pipe execution that is currently in progress.
        Once cancelled, a pipe cannot be resumed and must be started again if needed.
        Args:
            pipe_execution_id: The unique identifier for the pipe execution
        Returns:
            ApiResponse indicating success or failure of the cancellation
        Raises:
            HTTPException: If the request fails or returns a non-200 status code
        """
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipeline_run_id}/cancel", request=None)
        return ApiResponse(**response)

    @override
    async def get_pipeline_status(
        self,
        pipeline_run_id: str,
    ) -> PipeStatus:
        """
        Get the current status of a pipe execution.
        This method allows checking the current status of a pipe execution
        that was started with start_pipe.
        Args:
            pipe_execution_id: The unique identifier for the pipe execution
        Returns:
            PipeStatus with the current execution status and pipe output if completed
        Raises:
            HTTPException: If the request fails or returns a non-200 status code
        """
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipeline_run_id}/status", request=None)
        return cast(PipeStatus, kajson.loads(response))
        # raise NotImplementedError("Pipelex API functionality is coming soon!")
