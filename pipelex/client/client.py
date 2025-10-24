from typing import Any

import httpx
from typing_extensions import override

from pipelex.client.pipeline_request_factory import PipelineRequestFactory
from pipelex.client.pipeline_response_factory import PipelineResponseFactory
from pipelex.client.protocol import PipelexProtocol, PipelineInputs, PipelineRequest, PipelineRequestError, PipelineResponse
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity
from pipelex.exceptions import ClientAuthenticationError
from pipelex.system.environment import get_required_env


class PipelexClient(PipelexProtocol):
    """A client for interacting with Pipelex pipelines through the API.

    This client provides a user-friendly interface for executing pipelines through
    the remote API.

    Args:
        api_token: The API token to use for authentication. If not provided, it will be loaded from the PIPELEX_API_TOKEN environment variable.
        If the environment variable is not set, an error will be raised.

    """

    def __init__(
        self,
        api_token: str | None = None,
        api_base_url: str | None = None,
    ):
        self.api_token = api_token or get_required_env("PIPELEX_API_KEY")

        if not self.api_token:
            msg = "API token is required for API execution"
            raise ClientAuthenticationError(msg)

        self.api_base_url = api_base_url or get_required_env("PIPELEX_API_BASE_URL")
        if not self.api_base_url:
            msg = "API base URL is required for API execution"
            raise ClientAuthenticationError(msg)

        self.client: httpx.AsyncClient | None = None

    def start_client(self) -> "PipelexClient":
        """Initialize the HTTP client for API calls."""
        self.client = httpx.AsyncClient(base_url=self.api_base_url, headers={"Authorization": f"Bearer {self.api_token}"})
        return self

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            self.client = None

    async def _make_api_call(self, endpoint: str, request: str | None = None) -> dict[str, Any]:
        """Make an API call to the Pipelex server.

        Args:
            endpoint: The API endpoint to call, relative to the base URL
            request: A JSON-formatted string to send as the request body, or None if no body is needed
        Returns:
            dict[str, Any]: The JSON-decoded response from the server
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
        response_data: dict[str, Any] = response.json()
        return response_data

    @override
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
            pipe_code: The code identifying the pipeline to execute
            plx_content: Content of the pipeline bundle to execute
            inputs: Inputs passed to the pipeline
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for the dynamic output concept code
        Returns:
            PipelineResponse: Complete execution results including pipeline state and output

        """
        if not pipe_code and not plx_content:
            msg = "Either pipe_code or plx_content must be provided to the API execute_pipeline."
            raise PipelineRequestError(message=msg)

        working_memory: WorkingMemory | None = None
        pipeline_request: PipelineRequest | None = None
        if inputs is not None:
            if isinstance(inputs, WorkingMemory):
                working_memory = inputs
            else:
                working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=inputs)

        pipeline_request = PipelineRequestFactory.make_from_working_memory(
            pipe_code=pipe_code,
            plx_content=plx_content,
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call("v1/pipeline/execute", request=pipeline_request.model_dump_json())
        return PipelineResponseFactory.make_from_api_response(response)

    @override
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
            pipe_code: The code identifying the pipeline to execute
            plx_content: Content of the pipeline bundle to execute
            inputs: Inputs passed to the pipeline
            output_name: Name of the output slot to write to
            output_multiplicity: Output multiplicity setting
            dynamic_output_concept_code: Override for the dynamic output concept code
        Returns:
            PipelineResponse: Initial response with pipeline_run_id and created_at timestamp
        """
        if not pipe_code and not plx_content:
            msg = "Either pipe_code or plx_content must be provided to the API start_pipeline."
            raise PipelineRequestError(message=msg)

        working_memory: WorkingMemory | None = None
        pipeline_request: PipelineRequest | None = None
        if inputs is not None:
            if isinstance(inputs, WorkingMemory):
                working_memory = inputs
            else:
                working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(pipeline_inputs=inputs)

        pipeline_request = PipelineRequestFactory.make_from_working_memory(
            pipe_code=pipe_code,
            plx_content=plx_content,
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call("v1/pipeline/start", request=pipeline_request.model_dump_json())
        return PipelineResponseFactory.make_from_api_response(response)
