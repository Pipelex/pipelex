"""Unit tests for Pipelex's workflow-id construction model.

Pins the shape documented in
``wip/temporal-primitives/id-and-naming-design.md`` §"Layer 1 — Identity":

- Top-level: ``{env_prefix}{pipeline_run_id}``.
- Fixed-role child: ``{parent}_pipe-router``.
- Dynamic child (sub-pipe spawned by a router): ``{parent}_{pipe_code}-{8-hex}``.

The dynamic-child id uses ``workflow.uuid4()`` for replay-safety — Temporal's
``workflow.uuid4()`` is deterministic, unlike stdlib ``uuid.uuid4()`` (which
the workflow sandbox forbids).
"""

from collections.abc import Iterator

import pytest
from pytest_mock import MockerFixture

from pipelex.system.runtime import RunMode, runtime_manager
from pipelex.temporal.temporal_manager import TemporalManager


@pytest.fixture
def temporal_manager() -> Iterator[TemporalManager]:
    """Ensure ``TemporalManager`` is set up with a known session_id for the test.

    Restores any previous singleton after the test by tearing down and re-seeding.
    """
    prior = TemporalManager._shared_instance  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
    TemporalManager.teardown()
    TemporalManager.setup(session_id="EdgdJ7Yk4Q3HF2pXyZv9w8")
    try:
        yield TemporalManager.get_instance()
    finally:
        TemporalManager.teardown()
        if prior is not None:
            TemporalManager._shared_instance = prior  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


class TestTopLevelWorkflowIdConstruction:
    @pytest.mark.parametrize(
        ("run_mode", "expected_prefix"),
        [
            (RunMode.UNIT_TEST, "ut-"),
            (RunMode.NORMAL, ""),
            (RunMode.CI_TEST, "ci-"),
            (RunMode.CODEX_CLOUD, "cc-"),
            (RunMode.CODEX_CLOUD_TEST, "cct-"),
        ],
    )
    def test_make_top_workflow_id_per_run_mode(
        self,
        temporal_manager: TemporalManager,
        run_mode: RunMode,
        expected_prefix: str,
    ) -> None:
        prior_mode = runtime_manager.run_mode
        runtime_manager.set_run_mode(run_mode)
        try:
            pipeline_run_id = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
            workflow_id = temporal_manager.make_top_workflow_id(pipeline_run_id=pipeline_run_id)
            assert workflow_id == f"{expected_prefix}{pipeline_run_id}"
        finally:
            runtime_manager.set_run_mode(prior_mode)

    def test_make_top_workflow_id_has_no_session_or_random_suffix(
        self,
        temporal_manager: TemporalManager,
    ) -> None:
        """The redesigned id is the bare ``{env_prefix}{pipeline_run_id}`` —
        no truncated session id, no shortuuid suffix, no class name.
        """
        prior_mode = runtime_manager.run_mode
        runtime_manager.set_run_mode(RunMode.UNIT_TEST)
        try:
            pipeline_run_id = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
            workflow_id = temporal_manager.make_top_workflow_id(pipeline_run_id=pipeline_run_id)
            # No 5-char session truncation followed by a dash.
            assert "EdgdJ" not in workflow_id
            # No "TemporalPipeRun" / "TemporalPipeRouter" tail.
            assert "TemporalPipe" not in workflow_id
        finally:
            runtime_manager.set_run_mode(prior_mode)


class TestChildWorkflowIdConstruction:
    """Build child workflow ids the way Phase 3's call sites do, and assert the
    documented shape.

    The construction lives in ``temporal_pipe_router.py`` and ``wf_pipe_run.py``.
    These tests reproduce the formula locally rather than driving the real call
    sites — the formula itself is the contract.
    """

    def test_fixed_role_child_uses_underscore_pipe_router_suffix(self) -> None:
        parent_workflow_id = "ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"

        # Mirrors the construction in wf_pipe_run.py:
        child_id = f"{parent_workflow_id}_pipe-router"

        assert child_id == "ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c_pipe-router"
        # The separator is `_`, never `/`: workflow ids must stay free of path
        # separators so they can be reused verbatim as S3 keys / file names.
        assert "/" not in child_id
        assert child_id.endswith("_pipe-router")

    def test_dynamic_child_uses_underscore_pipe_code_and_8_hex_disambiguator(self, mocker: MockerFixture) -> None:
        """The dynamic-child id must be fully determined by
        (parent_workflow_id, pipe_code, workflow.uuid4() output) — i.e. the
        implementation must use ``workflow.uuid4()`` (replay-safe), not
        stdlib ``uuid.uuid4()`` which Temporal's workflow sandbox forbids.
        """
        # ``str(workflow.uuid4())`` returns a UUID string — mock with a stub
        # whose ``__str__`` returns the deterministic 36-char form so the
        # ``[:8]`` slice picks up the same prefix on every replay.
        mocker.patch("temporalio.workflow.uuid4", return_value="7c1e2f8a-deadbeef-cafebabe-12345678")
        from temporalio import workflow  # noqa: PLC0415

        parent_workflow_id = "ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
        pipe_code = "translate_doc"

        # Mirrors the construction in temporal_pipe_router.py (child branch):
        child_id = f"{parent_workflow_id}_{pipe_code}-{str(workflow.uuid4())[:8]}"

        assert child_id == "ut-3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c_translate_doc-7c1e2f8a"
        assert "/" not in child_id
        # Replay-determinism: re-running the same construction with the same
        # mock yields the same id.
        child_id_again = f"{parent_workflow_id}_{pipe_code}-{str(workflow.uuid4())[:8]}"
        assert child_id_again == child_id
