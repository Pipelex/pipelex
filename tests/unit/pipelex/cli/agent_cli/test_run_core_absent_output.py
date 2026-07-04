"""The agent CLI run core on an absent main output (Step E): the run is a success and the JSON
envelope carries an explicit absence payload (`"absent": true` + the record fields) instead of a
rendered value — never a crash on the missing stuff.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


class TestAgentRunCoreAbsentOutput:
    def test_absent_main_output_returns_absence_payload(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        monkeypatch: Any,
    ) -> None:
        """An absent main output flows through the compact envelope as an explicit absence doc."""
        monkeypatch.chdir(tmp_path)
        memory = WorkingMemory()
        memory.record_new_main_absence(
            AbsenceRecord(
                variable_name="summary",
                kind=AbsenceKind.DECLARED_ABSENT,
                reason="condition 'gate' evaluated to continue",
                producing_pipe="gate",
            )
        )
        pipe_output = SimpleNamespace(
            working_memory=memory,
            graph_spec=None,
            tokens_usages=None,
        )
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(return_value=SimpleNamespace(pipe_output=pipe_output))
        mocker.patch("pipelex.cli.agent_cli.commands.run._run_core.PipelexMTHDSProtocol", return_value=runner_mock)

        result = asyncio.run(run_pipeline_core("gate", costs=False))

        # Compact mode returns the payload directly — here, the explicit absence doc.
        assert result["absent"] is True
        assert result["variable_name"] == "summary"
        assert result["reason"] == "condition 'gate' evaluated to continue"

        # The on-disk output mirrors the envelope.
        disk_payload = json.loads((tmp_path / "mthds-wip" / "live_run.json").read_text(encoding="utf-8"))
        assert disk_payload["absent"] is True
