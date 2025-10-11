import os

import kajson
from typing_extensions import override

from pipelex.config import get_config
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType


class LocalObserver(ObserverProtocol):
    def __init__(self, storage_dir: str | None = None) -> None:
        self.storage_dir = storage_dir or get_config().pipelex.observer_config.observer_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _write_to_jsonl(self, event_type: str, payload: PayloadType) -> None:
        payload = {
            "event_type": event_type,
            **payload,
        }

        file_path = os.path.join(self.storage_dir, f"{event_type}.jsonl")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(kajson.dumps(payload) + "\n")

    @override
    async def observe_before_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("before_run", payload)

    @override
    async def observe_after_successful_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("successful_run", payload)

    @override
    async def observe_after_failing_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("failing_run", payload)
