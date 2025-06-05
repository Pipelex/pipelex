from typing import Any, Optional, cast

import httpx
from kajson import kajson
from typing_extensions import override

from pipelex.client.protocol import ApiResponse, PipelexProtocol, PipelineRequest, PipelineResponse, PipelineState
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import ClientAuthenticationError
from pipelex.tools.environment import get_required_env


class PipelexClient(PipelexProtocol):
    """
    A client for interacting with Pipelex pipelines through the API.

    This client provides a user-friendly interface for executing pipelines through
    the remote API.
    Args:
        api_token: The API token to use for authentication. If not provided, it will be loaded from the PIPELEX_API_TOKEN environment variable.
        If the environment variable is not set, an error will be raised.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
        api_base_url: Optional[str] = None,
    ):
        self.api_token = api_token or get_required_env("PIPELEX_API_TOKEN")

        if not self.api_token:
            raise ClientAuthenticationError("API token is required for API execution")

        self.api_base_url = api_base_url or get_required_env("PIPELEX_API_BASE_URL")
        if not self.api_base_url:
            raise ClientAuthenticationError("API base URL is required for API execution")

        self.client: Optional[httpx.AsyncClient] = None

    def start_client(self) -> "PipelexClient":
        """Initialize the HTTP client for API calls."""
        self.client = httpx.AsyncClient(base_url=self.api_base_url, headers={"Authorization": f"Bearer {self.api_token}"})
        return self

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

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
        if not self.client:
            self.start_client()
            assert self.client is not None

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
    ) -> PipelineResponse:
        """
        Execute a pipeline with the given request and wait for completion.
        This is a blocking operation that does not return until the pipeline execution
        is complete. For long-running pipelines, consider using start_pipeline instead.

        Args:
            pipe_code: The unique identifier for the pipeline to execute
            working_memory: Memory context passed to the pipeline
            output_name: Target output slot name
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for dynamic output concept

        Returns:
            PipelineResponse: Complete execution results including pipeline state and output

        Raises:
            HTTPException: If the API request fails or returns a non-200 status code
            ClientAuthenticationError: If API token is missing for API execution
        """
        pipeline_request = PipelineRequest(
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipe_code}/execute", request=kajson.dumps(pipeline_request))
        return cast(PipelineResponse, kajson.loads(response))

    @override
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
            pipe_code: The unique identifier for the pipeline to execute
            working_memory: Memory context passed to the pipeline
            output_name: Target output slot name
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for dynamic output concept

        Returns:
            PipelineResponse: Initial response with pipeline_run_id and created_at timestamp

        Raises:
            HTTPException: On pipeline start failure
            ClientAuthenticationError: If API token is missing for API execution
        """
        pipeline_request = PipelineRequest(
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipe_code}/start", request=kajson.dumps(pipeline_request))
        return cast(PipelineResponse, kajson.loads(response))

    @override
    async def cancel_pipeline(
        self,
        pipeline_run_id: str,
    ) -> ApiResponse:
        """
        Cancel a running pipeline execution.
        This method attempts to cancel a pipeline execution that is currently in progress.
        Once cancelled, a pipeline cannot be resumed and must be started again if needed.

        Args:
            pipeline_run_id: The unique identifier for the pipeline execution

        Returns:
            ApiResponse indicating success or failure of the cancellation

        Raises:
            HTTPException: If the request fails or returns a non-200 status code
            ClientAuthenticationError: If API token is missing
        """
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipeline_run_id}/cancel", request=None)
        return ApiResponse(**response)

    @override
    async def get_pipeline_state(
        self,
        pipeline_run_id: str,
    ) -> PipelineState:
        """
        Get the current status of a pipeline execution.
        This method allows checking the current status of a pipeline execution
        that was started with start_pipeline.

        Args:
            pipeline_run_id: The unique identifier for the pipeline execution

        Returns:
            PipelineState with the current execution status

        Raises:
            HTTPException: If the request fails or returns a non-200 status code
            ClientAuthenticationError: If API token is missing
        """
        response = await self._make_api_call(f"pipelex/v1/pipeline/{pipeline_run_id}/status", request=None)
        return cast(PipelineState, kajson.loads(response))
