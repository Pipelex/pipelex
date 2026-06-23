"""Regression tests: ``dry_run_pipeline`` owns its graph transport.

``dry_run_pipeline`` explicitly requests a graph (``generate_graph=True``), so producing it must
not depend on the host's ``tracing_config`` — the validation host that surfaced this (pipelex-api
in direct mode) ships ``tracing_config.is_enabled = false``, which used to leave the tracer with
no transport and the run with ``graph_spec=None``. The function now installs a scoped in-memory
event log around the run, so:

- with tracing **disabled**, the graph still comes back (the regression);
- with tracing **enabled**, the scoped override takes priority over the configured backend, so a
  validation dry-run writes no trace files (``make_event_log`` is never called).
"""

import pytest
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.interpreter.exceptions import PipelexInterpreterError
from pipelex.pipeline.dry_run_pipeline import dry_run_pipeline
from pipelex.system.configuration.configs import NdjsonTracingConfig, TracingBackend

_DRY_RUN_GRAPH_DOMAIN = "dry_run_pipeline_graph"
_DRY_RUN_GRAPH_MTHDS = f"""
domain = "{_DRY_RUN_GRAPH_DOMAIN}"
description = "Minimal bundle for dry_run_pipeline graph-transport tests"
main_pipe = "echo_subject"

[pipe.echo_subject]
type = "PipeLLM"
description = "Pipe used to exercise dry_run_pipeline graph generation"
output = "Text"
prompt = "Echo something"
"""

_DRY_RUN_GRAPH_NO_MAIN_MTHDS = f"""
domain = "{_DRY_RUN_GRAPH_DOMAIN}_no_main"
description = "No-main bundle for explicit dry_run_pipeline graph target tests"

[pipe.echo_subject]
type = "PipeLLM"
description = "Pipe used to exercise explicit graph target generation"
output = "Text"
prompt = "Echo something"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestDryRunPipelineGraphTransport:
    def _forbid_event_log_factory(self, mocker: MockerFixture) -> None:
        factory_error = AssertionError("make_event_log must not be called: dry_run_pipeline traces through its scoped in-memory log")
        mocker.patch("pipelex.pipeline.pipeline_run_setup.make_event_log", side_effect=factory_error)
        mocker.patch("pipelex.pipe_run.tracing_assembly.make_event_log", side_effect=factory_error)

    async def test_graph_produced_with_tracing_disabled(self, mocker: MockerFixture) -> None:
        """The pipelex-api regression: tracing off must not mean graph off."""
        mocker.patch.object(get_config().pipelex.tracing_config, "is_enabled", False)
        self._forbid_event_log_factory(mocker)

        graph_spec, pipe_code = await dry_run_pipeline(mthds_contents=[_DRY_RUN_GRAPH_MTHDS])

        assert pipe_code == f"{_DRY_RUN_GRAPH_DOMAIN}.echo_subject"
        traced_pipe_codes = {node.pipe_code for node in graph_spec.nodes if node.pipe_code}
        assert "echo_subject" in traced_pipe_codes
        assert "source" not in graph_spec.pipe_registry[f"{_DRY_RUN_GRAPH_DOMAIN}.echo_subject"]
        for concept_data in graph_spec.concept_registry.values():
            assert "source" not in concept_data

    async def test_scoped_log_takes_priority_over_enabled_backend(self, tmp_path_factory: pytest.TempPathFactory, mocker: MockerFixture) -> None:
        """With tracing enabled, the scoped in-memory log still owns the run — no trace files written."""
        cfg = get_config().pipelex.tracing_config
        traces_dir = tmp_path_factory.mktemp("dry_run_pipeline_traces")
        mocker.patch.object(cfg, "is_enabled", True)
        mocker.patch.object(cfg, "backend", TracingBackend.NDJSON)
        mocker.patch.object(cfg, "ndjson", NdjsonTracingConfig(traces_dir=str(traces_dir)))
        self._forbid_event_log_factory(mocker)

        graph_spec, _ = await dry_run_pipeline(mthds_contents=[_DRY_RUN_GRAPH_MTHDS])

        assert graph_spec.nodes
        assert not list(traces_dir.iterdir()), "the configured ndjson backend must not be touched"

    async def test_explicit_pipe_code_without_main_pipe_produces_graph(self, mocker: MockerFixture) -> None:
        """An explicit graph target removes the main_pipe requirement for graph generation."""
        mocker.patch.object(get_config().pipelex.tracing_config, "is_enabled", False)
        self._forbid_event_log_factory(mocker)

        graph_spec, pipe_code = await dry_run_pipeline(
            mthds_contents=[_DRY_RUN_GRAPH_NO_MAIN_MTHDS],
            pipe_code="echo_subject",
        )

        assert pipe_code == f"{_DRY_RUN_GRAPH_DOMAIN}_no_main.echo_subject"
        traced_pipe_codes = {node.pipe_code for node in graph_spec.nodes if node.pipe_code}
        assert traced_pipe_codes == {"echo_subject"}

    async def test_blank_explicit_pipe_code_is_rejected(self) -> None:
        """A blank explicit target must not silently fall back to main_pipe."""
        with pytest.raises(PipelexInterpreterError) as exc_info:
            await dry_run_pipeline(
                mthds_contents=[_DRY_RUN_GRAPH_MTHDS],
                pipe_code="   ",
            )

        assert str(exc_info.value) == "pipe_code must not be blank when provided"
