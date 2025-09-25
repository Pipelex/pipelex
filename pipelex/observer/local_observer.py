import json
import os
from typing import Optional

from typing_extensions import override

from pipelex.config import get_config
from pipelex.observer.observer_protocol import ObserverProtocol, PayloadType


class LocalObserver(ObserverProtocol):
    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self.storage_dir = storage_dir or get_config().pipelex.observer_config.observer_dir
        os.makedirs(self.storage_dir, exist_ok=True)

    def _write_to_jsonl(self, event_type: str, payload: PayloadType) -> None:
        timestamped_payload = {
            "event_type": event_type,
            **payload,
        }

        file_path = os.path.join(self.storage_dir, f"{event_type}.jsonl")
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(timestamped_payload) + "\n")

    @override
    async def before_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("before_run", payload)

    @override
    async def successful_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("successful_run", payload)

    @override
    async def failing_run(self, payload: PayloadType) -> None:
        self._write_to_jsonl("failing_run", payload)
