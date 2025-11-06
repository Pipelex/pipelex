from typing import Any, Protocol

from typing_extensions import override

from pipelex.types import StrEnum

PayloadType = dict[str, Any]


class PayloadKey(StrEnum):
    PIPELINE_RUN_ID = "pipeline_run_id"
    PIPE_JOB = "pipe_job"
    PIPE_OUTPUT = "pipe_output"
    ERROR = "error"


class ObserverProtocol(Protocol):
    async def observe_before_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload before the run"""
        ...

    async def observe_after_successful_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload after the run is successful"""
        ...

    async def observe_after_failing_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload after the run fails"""
        ...


class ObserverNoOp(ObserverProtocol):
    @override
    async def observe_before_run(self, payload: PayloadType) -> None:
        pass

    @override
    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        pass

    @override
    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        pass
