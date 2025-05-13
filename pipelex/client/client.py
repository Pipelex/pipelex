# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Optional

from pipelex.client.api_client import PipelexApiClient
from pipelex.client.protocol import (
    PipeRequest,
    PipeStartResponse,
    PipeState,
    PipeStatus,
)
from pipelex.exceptions import ClientAuthenticationError
from pipelex.run import run_pipe_code


class PipelexClient:
    """
    A high-level client for interacting with Pipelex pipes.

    This client provides a user-friendly interface for executing pipes either locally
    or through the remote API, with automatic handling of both modes.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
    ):
        """
        Initialize the PipelexClient.

        Args:
            api_token: Authentication token for the API
        """
        self.api_token = api_token
        self.api_client: Optional[PipelexApiClient] = None

    async def start_api_client(self) -> PipelexApiClient:
        """
        Start the API client.
        """
        if not self.api_token:
            raise ClientAuthenticationError("API token is required for API execution")

        self.api_client = PipelexApiClient(api_token=self.api_token).start_client()
        return self.api_client

    async def close_api_client(self):
        """
        Close the API client.
        """
        if self.api_client:
            await self.api_client.close()
            self.api_client = None

    async def execute_pipe(
        self,
        pipe_code: str,
        pipe_execute_request: PipeRequest,
        use_local_execution: bool = True,
    ) -> PipeStatus:
        """
        Execute a pipe with the given request and wait for completion.

        Args:
            pipe_code: The code of the pipe to execute
            pipe_execute_request: The request containing memory and output concept
            use_local_execution: Whether to execute locally (True) or via API (False)

        Returns:
            PipeStatus with execution results and pipe output
        """
        # Local execution
        if use_local_execution:
            pipe_output = await run_pipe_code(
                pipe_code=pipe_code,
                working_memory=pipe_execute_request.memory,
                output_concept_code=pipe_execute_request.output_concept,
            )
            return PipeStatus(
                pipe_execution_id="local",
                pipe_code=pipe_code,
                state=PipeState.COMPLETED,
                pipe_output=pipe_output,
            )
        # api_client = await self.start_api_client()
        # return await api_client.execute_pipe(pipe_code, pipe_execute_request)
        raise NotImplementedError("Pipelex API functionality is coming soon!")

    async def start_pipe(
        self,
        pipe_code: str,
        pipe_execute_request: PipeRequest,
    ) -> PipeStartResponse:
        """
        Start a pipe execution in the background without waiting for completion.

        This is a non-blocking operation that returns immediately with an execution ID.
        The execution will continue in the background, and the status can be checked
        using get_pipe_status. Note that this method always uses API execution.

        Args:
            pipe_code: The code of the pipe to execute
            pipe_execute_request: The request containing memory and output concept

        Returns:
            PipeStartResponse with the pipe_execution_id and created_at timestamp

        Raises:
            ValueError: If API token is not provided
            HTTPException: If the API request fails
        """
        # api_client = await self.start_api_client()
        # return await api_client.start_pipe(pipe_code, pipe_execute_request)
        raise NotImplementedError("Pipelex API functionality is coming soon!")

    async def get_pipe_status(
        self,
        pipe_execution_id: str,
    ) -> PipeStatus:
        """
        Get the current status of a pipe execution.

        This method allows checking the current status of a pipe execution
        that was started with start_pipe. Note that this method always uses
        API execution.

        Args:
            pipe_execution_id: The unique identifier for the pipe execution

        Returns:
            PipeStatus with the current execution status and pipe output if completed

        Raises:
            ValueError: If API token is not provided
            HTTPException: If the API request fails or the execution ID is invalid
        """
        # api_client = await self.start_api_client()
        # return await api_client.get_pipe_status(pipe_execution_id)
        raise NotImplementedError("Pipelex API functionality is coming soon!")
