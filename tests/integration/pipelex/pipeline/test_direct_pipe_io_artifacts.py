"""A DIRECT run builds its I/O artifacts inside its own library window and carries them on the output.

The three artifacts (`pipe_io_contracts`, `input_form`, `output_form`) describe the data a run's
`graph_spec` carries, and the builders need the run library, which `PipelineRunner.execute` tears
down before returning. So they are built at the end of `PipeRun.run`, right where the graph is
assembled, and gated by the graph: a run with graph tracing off has neither. A builder failure is
reported on `pipe_io_artifacts_error` (the `graph_assembly_error` pattern) and never fails the run.

Runs fully dry (`PipeRunMode.DRY` + `mock_inputs`), so no inference happens.
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.pipeline.exceptions import PipeIOContractError
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.configuration.configs import NdjsonTracingConfig, PipelineExecutionConfig, TracingBackend
from pipelex.system.pipe_run_mode import PipeRunMode

_DOMAIN = "direct_pipe_io_artifacts"
_MTHDS = f"""
domain = "{_DOMAIN}"
description = "Minimal bundle for the run-carried I/O artifacts"

[concept.Topic]
description = "A topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe whose run carries its I/O artifacts"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"

[pipe.other_entry]
type = "PipeLLM"
description = "A second entry pipe the graph never references"
inputs = {{ subject = "Text" }}
output = "Text"
prompt = "Say $subject"
"""


def _config(*, generate_graph: bool, graphspec_json: bool = True) -> PipelineExecutionConfig:
    config = get_config().interpreter.pipeline_execution.with_execution_overrides(
        generate_graph=generate_graph,
        generate_usage=False,
        mock_inputs=True,
    )
    inclusion = config.graph.graphs_inclusion.model_copy(update={"graphspec_json": graphspec_json})
    return config.model_copy(update={"graph": config.graph.model_copy(update={"graphs_inclusion": inclusion})})


@pytest.mark.asyncio(loop_scope="class")
class TestDirectPipeIOArtifacts:
    def _enable_ndjson_tracing(self, mocker: MockerFixture, traces_dir: str) -> None:
        cfg = get_config().runtime.tracing
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=traces_dir))

    async def _run(self, execution_config: PipelineExecutionConfig) -> PipeOutput:
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, execution_config=execution_config)
        response = await runner.execute(pipe_code="echo_topic", mthds_contents=[_MTHDS])
        return response.pipe_output

    async def test_graph_on_carries_artifacts_keyed_by_the_whole_run_library(
        self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture
    ) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_artifacts_on")))

        pipe_output = await self._run(_config(generate_graph=True))

        assert pipe_output.graph_spec is not None
        artifacts = pipe_output.pipe_io_artifacts
        assert artifacts is not None
        assert pipe_output.pipe_io_artifacts_error is None
        # Every pipe the graph names is described...
        assert set(pipe_output.graph_spec.pipe_registry) <= set(artifacts.pipe_io_contracts)
        # ...and so is every other pipe of the run library, for a consumer driving a run form from it.
        assert f"{_DOMAIN}.echo_topic" in artifacts.pipe_io_contracts
        assert f"{_DOMAIN}.other_entry" in artifacts.pipe_io_contracts
        assert set(artifacts.pipe_io_contracts) == set(artifacts.input_form) == set(artifacts.output_form)

    async def test_graph_off_carries_no_artifacts(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """The artifacts exist to describe a graph's data: no graph, no artifacts, and no error either."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_artifacts_off")))

        pipe_output = await self._run(_config(generate_graph=False))

        assert pipe_output.graph_spec is None
        assert pipe_output.pipe_io_artifacts is None
        assert pipe_output.pipe_io_artifacts_error is None

    async def test_builder_failure_is_reported_on_the_output_and_the_run_succeeds(
        self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture
    ) -> None:
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_artifacts_fail")))
        # Patched on the module `PipeRun.run` imports it into, so the failure is the builder's, not the run's.
        mocker.patch(
            "pipelex.pipe_run.pipe_run.build_pipe_io_artifacts",
            side_effect=PipeIOContractError(message="simulated render failure"),
        )

        pipe_output = await self._run(_config(generate_graph=True))

        assert pipe_output.graph_spec is not None
        assert pipe_output.pipe_io_artifacts is None
        assert pipe_output.pipe_io_artifacts_error is not None
        assert "simulated render failure" in pipe_output.pipe_io_artifacts_error

    async def test_graphspec_json_off_carries_no_artifacts(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """The artifacts are the graphspec's companions: a run that writes no graphspec builds none, whatever else it renders."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_artifacts_no_graphspec")))
        builder = mocker.patch("pipelex.pipe_run.pipe_run.build_pipe_io_artifacts")

        pipe_output = await self._run(_config(generate_graph=True, graphspec_json=False))

        assert pipe_output.graph_spec is not None
        assert pipe_output.pipe_io_artifacts is None
        assert pipe_output.pipe_io_artifacts_error is None
        builder.assert_not_called()

    async def test_an_unexpected_builder_error_is_reported_and_the_run_succeeds(
        self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture
    ) -> None:
        """A bug in the builders is reported like their own failures: the build runs in the `finally` ahead of the delivery and must never escape."""
        self._enable_ndjson_tracing(mocker, str(tmp_path_factory.mktemp("traces_artifacts_bug")))
        mocker.patch("pipelex.pipe_run.pipe_run.build_pipe_io_artifacts", side_effect=TypeError("a bug in the builder"))

        pipe_output = await self._run(_config(generate_graph=True))

        assert pipe_output.graph_spec is not None
        assert pipe_output.pipe_io_artifacts is None
        assert pipe_output.pipe_io_artifacts_error is not None
        assert "a bug in the builder" in pipe_output.pipe_io_artifacts_error

    async def test_validate_does_not_build_the_artifacts_a_second_time(self, mocker: MockerFixture) -> None:
        """Validate builds the artifacts once, for its report; its graph dry run must not build a set it throws away."""
        run_hook_builder = mocker.patch("pipelex.pipe_run.pipe_run.build_pipe_io_artifacts")

        report = await validate_bundles_in_process(mthds_contents=[_MTHDS], graph_pipe_code=f"{_DOMAIN}.echo_topic")

        assert report.graph_spec is not None
        assert f"{_DOMAIN}.echo_topic" in report.pipe_io_contracts
        run_hook_builder.assert_not_called()
