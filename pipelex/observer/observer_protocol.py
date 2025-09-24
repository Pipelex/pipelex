from typing import Any, Dict, Protocol

PayloadType = Dict[str, Any]


class ObserverProtocol(Protocol):
    async def push(
        self,
        payload: PayloadType,
    ) -> None: ...
