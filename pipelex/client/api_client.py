from typing import Optional

from typing_extensions import override

from pipelex.client.protocol import (
    ApiResponse,
    PipelexProtocol,
    PipeStartResponse,
    PipeStatus,
)
from pipelex.core.pipe_run_params import PipeOutputMultiplicity
from pipelex.core.working_memory import WorkingMemory


class PipelexApiClient(PipelexProtocol):
    """
    API client for interacting with the Pipelex API.
    """

    def __init__(self, api_token: str):
        self.api_token = api_token

    def start_client(self) -> "PipelexApiClient":
        return self

    async def close(self):
        pass

    @override
    async def execute_pipeline(
        self,
        pipe_code: str,
        working_memory: Optional[WorkingMemory] = None,
        output_name: Optional[str] = None,
        output_multiplicity: Optional[PipeOutputMultiplicity] = None,
        dynamic_output_concept_code: Optional[str] = None,
    ) -> PipeStatus:
        raise NotImplementedError("Pipelex API functionality is coming soon!")

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
    async def cancel_pipeline(self, pipeline_run_id: str) -> ApiResponse:
        raise NotImplementedError("Pipelex API functionality is coming soon!")

    @override
    async def get_pipeline_status(self, pipeline_run_id: str) -> PipeStatus:
        raise NotImplementedError("Pipelex API functionality is coming soon!")
