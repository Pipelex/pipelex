from typing import Any, Protocol

PayloadType = dict[str, Any]


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
