"""`pipelex-agent run` writes its outputs into a numbered folder under `results/` beside its bundle, kept out of the method tree."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING

from mthds.method_tree.lister import list_method_tree

from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

BUNDLE = 'domain = "folder_probe"\nmain_pipe = "gate"\n'


class TestAgentRunCoreOutputFolder:
    def test_two_runs_beside_the_bundle_leave_its_method_tree_unchanged(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """Each run gets its own ignored folder, so the second run reads the tree the first read, with the same digest."""
        memory = WorkingMemory()
        memory.record_new_main_absence(
            AbsenceRecord(variable_name="summary", kind=AbsenceKind.DECLARED_ABSENT, reason="nothing to say", producing_pipe="gate")
        )
        pipe_output = SimpleNamespace(working_memory=memory, graph_spec=None, tokens_usages=None)
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(return_value=SimpleNamespace(pipe_output=pipe_output))
        mocker.patch("pipelex.cli.agent_cli.commands.run._run_core.PipelexMTHDSProtocol", return_value=runner_mock)
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        bundle_path = method_dir / "bundle.mthds"
        bundle_path.write_text(BUNDLE, encoding="utf-8")
        tree_before = list_method_tree(method_dir)

        for _ in range(2):
            asyncio.run(
                run_pipeline_core(
                    "folder_probe.gate",
                    mthds_contents=[BUNDLE],
                    bundle_uris=[str(bundle_path)],
                    costs=False,
                    method_tree=list_method_tree(method_dir),
                )
            )

        tree_after = list_method_tree(method_dir)
        assert tree_after.digest == tree_before.digest
        assert tree_after.tree_paths == ["bundle.mthds"]
        for run_folder_name in ("gate_output_01", "gate_output_02"):
            run_folder = method_dir / "results" / run_folder_name
            assert (run_folder / ".gitignore").is_file()
            assert json.loads((run_folder / "live_run.json").read_text(encoding="utf-8"))["method_tree_digest"] == tree_before.digest
