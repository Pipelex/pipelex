from typing import Any, Dict, Protocol

PayloadType = Dict[str, Any]


class ObserverProtocol(Protocol):
    async def before_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload before the run"""
        ...

    async def successful_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload after the run is successful"""
        ...

    async def failing_run(
        self,
        payload: PayloadType,
    ) -> None:
        """Process and store the payload after the run fails"""
        ...
