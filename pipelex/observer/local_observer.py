import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from typing_extensions import override

from pipelex.observer.observer_protocol import ObserverProtocol


class LocalObservability(ObserverProtocol):
    def __init__(self, storage_dir: Optional[str] = None) -> None:
        self.storage_dir = Path(storage_dir or ".pipelex/observer")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _get_daily_file_path(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.storage_dir / f"pipe_logs_{today}.jsonl"

    def _serialize_payload(self, payload: Dict[str, Any]) -> str:
        serializable_payload = {
            **payload,
            "timestamp": datetime.now().isoformat(),
        }
        return json.dumps(serializable_payload, default=str)

    @override
    async def push(
        self,
        payload: Dict[str, Any],
    ) -> None:
        file_path = self._get_daily_file_path()
        serialized_payload = self._serialize_payload(payload)

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(serialized_payload + "\n")
