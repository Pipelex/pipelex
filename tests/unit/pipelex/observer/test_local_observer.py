"""Unit tests for LocalObserver: JSONL persistence of run lifecycle events."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.observer.local_observer import LocalObserver, LocalObserverEventType

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

MODULE = "pipelex.observer.local_observer"


def _read_jsonl_lines(file_path: Path) -> list[dict[str, Any]]:
    """Parse each line of a JSONL file into a dict."""
    lines = file_path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


@pytest.mark.asyncio(loop_scope="class")
class TestLocalObserver:
    async def test_constructor_with_explicit_str_dir_creates_directory(self, tmp_path: Path) -> None:
        """An explicit storage_dir given as str is created on construction, parents included."""
        storage_dir = tmp_path / "nested" / "obs"

        observer = LocalObserver(storage_dir=str(storage_dir))

        assert observer.storage_dir == storage_dir
        assert storage_dir.is_dir()

    async def test_constructor_with_explicit_path_dir_creates_directory(self, tmp_path: Path) -> None:
        """An explicit storage_dir given as Path is created on construction, parents included."""
        storage_dir = tmp_path / "nested" / "obs"

        observer = LocalObserver(storage_dir=storage_dir)

        assert observer.storage_dir == storage_dir
        assert storage_dir.is_dir()

    async def test_constructor_default_dir_comes_from_config(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Without an explicit storage_dir, the directory comes from the observer config."""
        default_dir = tmp_path / "configured" / "observer"
        config_stub = SimpleNamespace(runtime=SimpleNamespace(observer=SimpleNamespace(observer_dir=str(default_dir))))
        get_config_mock = mocker.patch(f"{MODULE}.get_config", return_value=config_stub)

        observer = LocalObserver()

        get_config_mock.assert_called_once_with()
        assert observer.storage_dir == default_dir
        assert default_dir.is_dir()

    @pytest.mark.parametrize(
        ("method_name", "event_type"),
        [
            ("observe_before_run", LocalObserverEventType.BEFORE_RUN),
            ("observe_after_successful_run", LocalObserverEventType.AFTER_SUCCESSFUL_RUN),
            ("observe_after_failing_run", LocalObserverEventType.AFTER_FAILING_RUN),
        ],
    )
    async def test_observe_writes_one_jsonl_line_with_event_type(
        self,
        tmp_path: Path,
        method_name: str,
        event_type: LocalObserverEventType,
    ) -> None:
        """Each observe method appends exactly one line to {event_type}.jsonl merging event_type with the payload."""
        observer = LocalObserver(storage_dir=tmp_path / "obs")
        payload: dict[str, Any] = {"pipeline_run_id": "run-42", "step_count": 3}

        await getattr(observer, method_name)(payload)

        jsonl_path = tmp_path / "obs" / f"{event_type}.jsonl"
        records = _read_jsonl_lines(jsonl_path)
        assert records == [{"event_type": str(event_type), "pipeline_run_id": "run-42", "step_count": 3}]

    async def test_two_observe_calls_append_two_lines_in_order(self, tmp_path: Path) -> None:
        """Two calls on the same event type append two independently parseable lines, in call order."""
        observer = LocalObserver(storage_dir=tmp_path / "obs")

        await observer.observe_before_run({"pipeline_run_id": "run-1"})
        await observer.observe_before_run({"pipeline_run_id": "run-2"})

        jsonl_path = tmp_path / "obs" / f"{LocalObserverEventType.BEFORE_RUN}.jsonl"
        records = _read_jsonl_lines(jsonl_path)
        assert records == [
            {"event_type": str(LocalObserverEventType.BEFORE_RUN), "pipeline_run_id": "run-1"},
            {"event_type": str(LocalObserverEventType.BEFORE_RUN), "pipeline_run_id": "run-2"},
        ]

    async def test_event_name_wins_over_payload_event_type_key(self, tmp_path: Path) -> None:
        """A payload carrying its own event_type cannot overwrite the lifecycle event name in the written record."""
        observer = LocalObserver(storage_dir=tmp_path / "obs")
        payload: dict[str, Any] = {"event_type": "custom_override", "pipeline_run_id": "run-9"}

        await observer.observe_after_failing_run(payload)

        jsonl_path = tmp_path / "obs" / f"{LocalObserverEventType.AFTER_FAILING_RUN}.jsonl"
        records = _read_jsonl_lines(jsonl_path)
        assert records == [{"event_type": str(LocalObserverEventType.AFTER_FAILING_RUN), "pipeline_run_id": "run-9"}]
