"""Guard for ``GraphTracerManager.open_tracer``'s stale-key healing (audit fix M1).

A stale tracer under the requested key can only be the leftover of a prior interrupted
execution (e.g. a Temporal workflow evicted before its finally-block ``close_tracer``
ran). Pre-M1 this raised ``ValueError`` — letting worker-local leak state decide whether
a fresh run's tracing setup succeeds, a replay-determinism breach. ``WfPipeRouter``
dropped its best-effort guard around tracing setup on the strength of the pop-and-replace
contract pinned here.
"""

import logging

import pytest
from pytest_mock import MockerFixture

from pipelex.graph.graph_config import DataInclusionConfig
from pipelex.graph.graph_tracer_manager import GraphTracerManager

_DATA_INCLUSION_OFF = DataInclusionConfig(
    pipe_and_concept_registry=False,
    stuff_json_content=False,
    stuff_text_content=False,
    stuff_html_content=False,
    error_stack_traces=False,
)

_TRACER_KEY = "run_under_test"


class TestGraphTracerManagerStaleKeyHealing:
    @pytest.fixture(autouse=True)
    def fresh_singleton(self):
        GraphTracerManager.clear_instance()
        yield
        GraphTracerManager.clear_instance()

    def _open_tracer(self, manager: GraphTracerManager) -> None:
        manager.open_tracer(
            graph_id="pipeline_run_x",
            data_inclusion=_DATA_INCLUSION_OFF,
            workflow_id=_TRACER_KEY,
            pipeline_run_id="pipeline_run_x",
            tracer_key=_TRACER_KEY,
            emit_graph_events=False,
            emit_usage_events=True,
        )

    def test_open_tracer_replaces_stale_tracer_under_same_key(self, caplog: pytest.LogCaptureFixture) -> None:
        """Opening over a stale key must self-heal: warn, evict the stale tracer, register a fresh one."""
        manager = GraphTracerManager.get_or_create_instance()
        self._open_tracer(manager)
        stale_tracer = manager.get_tracer(_TRACER_KEY)
        assert stale_tracer is not None

        with caplog.at_level(logging.WARNING):
            # Pre-M1 this raised ValueError; it must now pop-and-replace.
            self._open_tracer(manager)

        fresh_tracer = manager.get_tracer(_TRACER_KEY)
        assert fresh_tracer is not None
        assert fresh_tracer is not stale_tracer, "the stale tracer must be evicted, not reused"
        assert "already exists" in caplog.text

    def test_open_tracer_heals_even_when_stale_teardown_raises(self, mocker: MockerFixture, caplog: pytest.LogCaptureFixture) -> None:
        """A stale tracer's raising teardown must not fail the fresh run's setup.

        The stale teardown runs graph assembly over arbitrary half-built state from an
        interrupted execution; letting its exception propagate would make a fresh run's
        tracing setup depend on leaked predecessor state — the M1 class all over again.
        """
        manager = GraphTracerManager.get_or_create_instance()
        self._open_tracer(manager)
        stale_tracer = manager.get_tracer(_TRACER_KEY)
        assert stale_tracer is not None
        mocker.patch.object(stale_tracer, "teardown", side_effect=RuntimeError("half-built state"))

        with caplog.at_level(logging.WARNING):
            # Must not raise despite the stale teardown blowing up.
            self._open_tracer(manager)

        fresh_tracer = manager.get_tracer(_TRACER_KEY)
        assert fresh_tracer is not None
        assert fresh_tracer is not stale_tracer, "the stale tracer must be evicted even when its teardown raises"

    def test_open_tracer_fresh_key_does_not_warn(self, caplog: pytest.LogCaptureFixture) -> None:
        """The healing warning must be gated on key membership: a fresh key opens silently."""
        manager = GraphTracerManager.get_or_create_instance()
        with caplog.at_level(logging.WARNING):
            self._open_tracer(manager)
        assert "already exists" not in caplog.text
        assert manager.get_tracer(_TRACER_KEY) is not None
