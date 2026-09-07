"""The agent CLI settles its graph outputs before the run, not at render time.

The run setup gates the graphspec's companion artifacts (`pipe_io_contracts`, `input_form`,
`output_form`) on the same `graphspec_json` inclusion flag that decides whether a graphspec is
written, and builds them inside the run's library window. A render-time override of that flag
would come too late: the graphspec would be written and its companions never built.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from pipelex.cli.agent_cli.commands.run._run_core import run_pipeline_core  # pyright: ignore[reportPrivateUsage]
from pipelex.config import get_config
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture

    from pipelex.system.configuration.configs import PipelineExecutionConfig

_RUN_CORE_MODULE = "pipelex.cli.agent_cli.commands.run._run_core"


def _execution_config_with_graphspec_json(*, graphspec_json: bool) -> PipelineExecutionConfig:
    execution_config = get_config().interpreter.pipeline_execution
    graphs_inclusion = execution_config.graph.graphs_inclusion.model_copy(update={"graphspec_json": graphspec_json})
    return execution_config.model_copy(update={"graph": execution_config.graph.model_copy(update={"graphs_inclusion": graphs_inclusion})})


class TestAgentRunCoreGraphInclusion:
    def _run_with_configured_graphspec(self, mocker: MockerFixture, *, graphspec_json: bool, graph: bool) -> Any:
        """Run the core with `graphspec_json` configured as given; return the execution config the runner received."""
        config = get_config().model_copy(
            update={
                "interpreter": get_config().interpreter.model_copy(
                    update={"pipeline_execution": _execution_config_with_graphspec_json(graphspec_json=graphspec_json)}
                )
            }
        )
        mocker.patch(f"{_RUN_CORE_MODULE}.get_config", return_value=config)
        memory = WorkingMemory()
        memory.record_new_main_absence(
            AbsenceRecord(variable_name="answer", kind=AbsenceKind.DECLARED_ABSENT, reason="not the point of this test", producing_pipe="answer")
        )
        pipe_output = SimpleNamespace(working_memory=memory, graph_spec=None, tokens_usages=None)
        runner_mock = mocker.MagicMock()
        runner_mock.execute = mocker.AsyncMock(return_value=SimpleNamespace(pipe_output=pipe_output))
        runner_class = mocker.patch(f"{_RUN_CORE_MODULE}.PipelexMTHDSProtocol", return_value=runner_mock)

        asyncio.run(run_pipeline_core("answer", graph=graph, costs=False))

        return runner_class.call_args.kwargs["execution_config"]

    def test_graph_on_forces_the_graphspec_before_the_run(self, mocker: MockerFixture, tmp_path: Path, monkeypatch: Any) -> None:
        """With `graphspec_json = false` configured, `--graph` still runs with the graphspec on, so its companions are built in the window."""
        monkeypatch.chdir(tmp_path)

        execution_config = self._run_with_configured_graphspec(mocker, graphspec_json=False, graph=True)

        assert execution_config.is_generate_graph is True
        assert execution_config.graph.graphs_inclusion.graphspec_json is True
        assert execution_config.graph.graphs_inclusion.reactflow_html is True
        assert execution_config.graph.graphs_inclusion.mermaidflow_html is False

    def test_graph_off_leaves_the_configured_inclusion_alone(self, mocker: MockerFixture, tmp_path: Path, monkeypatch: Any) -> None:
        """Without `--graph` nothing is rendered, so the configured inclusion is passed through untouched."""
        monkeypatch.chdir(tmp_path)

        execution_config = self._run_with_configured_graphspec(mocker, graphspec_json=False, graph=False)

        assert execution_config.is_generate_graph is False
        assert execution_config.graph.graphs_inclusion.graphspec_json is False
