# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Optional, cast

import httpx
from kajson import kajson
from typing_extensions import override

from pipelex.client.protocol import (
    ApiResponse,
    PipelexProtocol,
    PipeRequest,
    PipeStartResponse,
    PipeStatus,
)
from pipelex.tools.environment import get_required_env


class PipelexApiClient(PipelexProtocol):
    """
    A protocol-compliant client for interacting with Pipelex pipes via API.

    This client implements the PipelexProtocol interface for pure API communication.
    """

    def __init__(
        self,
        api_token: str,
    ):
        """
        Initialize the PipelexApiClient.

        Args:
            api_token: Authentication token for the API
        """
        self.api_token = api_token
        self.api_base_url = get_required_env("EV_API_BASE_URL")

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
        response = await self.client.post(f"/{endpoint}", content=content, headers={"Content-Type": "application/json"}, timeout=120.0)
        response.raise_for_status()
        return response.json()

    @override
    async def execute_pipe(
        self,
        pipe_code: str,
        request: PipeRequest,
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
        response = await self._make_api_call(f"pipelex/v1/pipes/{pipe_code}/execute", request=kajson.dumps(request))
        return cast(PipeStatus, kajson.loads(response))

    @override
    async def start_pipe(
        self,
        pipe_code: str,
        request: PipeRequest,
    ) -> PipeStartResponse:
        """
        Start a pipe execution in the background without waiting for completion.

        This is a non-blocking operation that returns immediately with an execution ID.
        The execution will continue in the background, and the status can be checked
        using get_pipe_status.

        Args:
            pipe_code: The unique identifier for the pipe to execute
            request: PipeRequest containing memory and output concept

        Returns:
            PipeStartResponse with the pipe_execution_id and created_at timestamp

        Raises:
            HTTPException: If the request fails or returns a non-200 status code
        """
        response = await self._make_api_call(f"pipelex/v1/pipes/{pipe_code}/start", request=kajson.dumps(request))
        return cast(PipeStartResponse, kajson.loads(response))

    @override
    async def get_pipe_status(
        self,
        pipe_execution_id: str,
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
        response = await self._make_api_call(f"pipelex/v1/pipes/{pipe_execution_id}/status", request=None)
        return cast(PipeStatus, kajson.loads(response))

    @override
    async def cancel_pipe(
        self,
        pipe_execution_id: str,
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
        response = await self._make_api_call(f"pipelex/v1/pipes/{pipe_execution_id}/cancel", request=None)
        return ApiResponse(**response)
