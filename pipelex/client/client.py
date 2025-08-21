from typing import Any, Optional

import httpx
from typing_extensions import override

from pipelex.client.pipeline_request_factory import PipelineRequestFactory
from pipelex.client.pipeline_response_factory import PipelineResponseFactory
from pipelex.client.protocol import CompactMemory, PipelexProtocol, PipelineResponse
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.pipes.pipe_run_params import PipeOutputMultiplicity
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
        input_memory: Optional[CompactMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipelineResponse:
        if working_memory and input_memory:
            raise ValueError(f"working_memory and input_memory cannot be provided together to the API execute_pipeline {pipe_code=}")

        if input_memory is not None:
            working_memory = WorkingMemoryFactory.make_from_compact_memory(input_memory)
        pipeline_request = PipelineRequestFactory.make_from_working_memory(
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call(f"v1/pipeline/{pipe_code}/execute", request=pipeline_request.model_dump_json())
        return PipelineResponseFactory.make_from_api_response(response)

    @override
    async def start_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        input_memory: Optional[CompactMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipelineResponse:
        if working_memory and input_memory:
            raise ValueError(f"working_memory and input_memory cannot be provided together to the API start_pipeline {pipe_code=}")

        if input_memory is not None:
            working_memory = WorkingMemoryFactory.make_from_compact_memory(input_memory)

        pipeline_request = PipelineRequestFactory.make_from_working_memory(
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )
        response = await self._make_api_call(f"v1/pipeline/{pipe_code}/start", request=pipeline_request.model_dump_json())
        return PipelineResponseFactory.make_from_api_response(response)
