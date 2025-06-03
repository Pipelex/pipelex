from datetime import datetime, timezone
from typing import Optional

from typing_extensions import override

from pipelex.client.api_client import PipelexApiClient
from pipelex.client.protocol import (
    ApiResponse,
    PipelexProtocol,
    PipeStartResponse,
    PipeState,
    PipeStatus,
)
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory
from pipelex.exceptions import ClientAuthenticationError
from pipelex.pipeline.execute import execute_pipeline as execute_pipeline
from pipelex.pipeline.start import start_pipeline as start_pipeline


class PipelexClient(PipelexProtocol):
    """
    A high-level client for interacting with Pipelex pipelines.

    This client provides a user-friendly interface for executing pipelines either locally
    or through the remote API, with automatic handling of both modes.
    """

    def __init__(
        self,
        api_token: Optional[str] = None,
    ):
        self.api_token = api_token
        self.api_client: Optional[PipelexApiClient] = None

    async def start_api_client(self) -> PipelexApiClient:
        if not self.api_token:
            raise ClientAuthenticationError("API token is required for API execution")

        self.api_client = PipelexApiClient(api_token=self.api_token)
        return self.api_client

    async def close_api_client(self):
        if self.api_client:
            await self.api_client.close()
            self.api_client = None

    @override
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
        use_local_execution: bool = True,
    ) -> PipeStatus:
        # Local execution
        if use_local_execution:
            pipe_output, pipeline_run_id = await execute_pipeline(
                pipe_code=pipe_code,
                working_memory=working_memory,
                output_name=output_name,
                output_multiplicity=output_multiplicity,
                dynamic_output_concept_code=dynamic_output_concept_code,
            )
            return PipeStatus(
                pipe_execution_id=pipeline_run_id,
                pipe_code=pipe_code,
                state=PipeState.COMPLETED,
                pipe_output=pipe_output,
            )

        # API execution
        api_client = await self.start_api_client()
        return await api_client.execute_pipeline(
            pipe_code=pipe_code,
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @override
    async def start_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
        use_local_execution: bool = True,
    ) -> PipeStartResponse:
        # Local execution
        if use_local_execution:
            pipeline_run_id, _ = await start_pipeline(
                pipe_code=pipe_code,
                working_memory=working_memory,
                output_name=output_name,
                output_multiplicity=output_multiplicity,
                dynamic_output_concept_code=dynamic_output_concept_code,
            )

            created_at = datetime.now(timezone.utc).isoformat()

            return PipeStartResponse(
                status="success",
                pipe_execution_id=pipeline_run_id,
                created_at=created_at,
            )

        # API execution
        api_client = await self.start_api_client()
        return await api_client.start_pipeline(
            pipe_code=pipe_code,
            working_memory=working_memory,
            output_name=output_name,
            output_multiplicity=output_multiplicity,
            dynamic_output_concept_code=dynamic_output_concept_code,
        )

    @override
    async def cancel_pipeline(self, pipeline_run_id: str) -> ApiResponse:
        api_client = await self.start_api_client()
        return await api_client.cancel_pipeline(pipeline_run_id)

    @override
    async def get_pipeline_status(self, pipeline_run_id: str) -> PipeStatus:
        api_client = await self.start_api_client()
        return await api_client.get_pipeline_status(pipeline_run_id)
