"""Unit test pinning that ``TemporalPipeRouter`` passes the same observability
kwargs on child workflow dispatch as on top-level dispatch.

Regression for PR #891 review feedback: the child path was passing
``static_summary`` but not ``static_details``, so child workflows showed no
details pane in the Temporal UI. The top-level path at
``temporal_pipe_router.py:108-115`` already passes both — the child path at
``temporal_pipe_router.py:81-88`` must mirror that surface.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.temporal.tprl.observability import build_static_details, build_static_summary
from pipelex.temporal.tprl_pipe.temporal_pipe_router import TemporalPipeRouter

_STUB_SESSION_ID = "EdgdJ7Yk4Q3HF2pXyZv9w8"


def _make_pipe_job_stub(mocker: MockerFixture) -> Any:
    """Stub PipeJob shaped for the helpers the router calls during child dispatch.

    Covers ``prepare_for_temporal()`` (returns self), ``pipe.code``,
    ``pipe.domain_code``, ``pipe.description``, ``pipe.inputs.root``,
    ``job_metadata.*``, and ``library_crate`` (``None`` so rehydrate skips
    the crate path).
    """
    pipe_job = mocker.MagicMock()
    pipe_job.prepare_for_temporal.return_value = pipe_job
    pipe_job.pipe.code = "translate_doc"
    pipe_job.pipe.domain_code = "documents"
    pipe_job.pipe.description = "Translate a document from English to French"
    pipe_job.pipe.inputs.root = {}
    pipe_job.job_metadata.user_id = "acme-corp"
    pipe_job.job_metadata.pipeline_run_id = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
    pipe_job.job_metadata.session_id = _STUB_SESSION_ID
    pipe_job.library_crate = None
    return pipe_job


@pytest.mark.asyncio(loop_scope="class")
class TestTemporalPipeRouterChildObservability:
    @pytest.fixture(autouse=True)
    def _enable_temporal(self, mocker: MockerFixture) -> None:
        """The async-enabled guard inside ``with_conditional_worker`` runs
        before ``_run_pipe_job``'s body — patch the decorator's ``get_config``
        site so the guard reads enabled (disabled-path coverage lives in
        ``test_async_execution_not_enabled.py``).
        """
        config_root = mocker.MagicMock()
        config_root.temporal.is_enabled = True
        mocker.patch("pipelex.temporal.tprl.conditional_worker.get_config", return_value=config_root)

    async def test_child_workflow_dispatch_passes_static_details(self, mocker: MockerFixture) -> None:
        """Child workflow dispatch must pass ``static_details`` to
        ``workflow.execute_child_workflow``, matching the top-level path.

        Without this kwarg the Temporal UI shows no details pane for child
        workflows even though the parent renders the full identity-field
        markdown table.
        """
        pipe_job = _make_pipe_job_stub(mocker)

        config_root = mocker.MagicMock()
        config_root.temporal.search_attributes.enabled = True
        config_root.temporal.search_attributes.attributes = ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
        mocker.patch("pipelex.temporal.tprl.observability.get_config", return_value=config_root)

        manager = mocker.MagicMock()
        manager.session_id = _STUB_SESSION_ID
        mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)

        mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_router.is_in_temporal_workflow", return_value=True)
        info_stub = mocker.MagicMock()
        info_stub.workflow_id = "ut-parent-wf-id"
        mocker.patch("pipelex.temporal.tprl_pipe.temporal_pipe_router.workflow.info", return_value=info_stub)
        mocker.patch(
            "pipelex.temporal.tprl_pipe.temporal_pipe_router.workflow.uuid4",
            return_value="deadbeef-aaaa-bbbb-cccc-ddddeeeeffff",
        )

        mock_execute_child = mocker.patch(
            "pipelex.temporal.tprl_pipe.temporal_pipe_router.workflow.execute_child_workflow",
            new_callable=mocker.AsyncMock,
        )
        sentinel_output = mocker.MagicMock()
        mock_execute_child.return_value = sentinel_output

        # Rehydrate is exercised by other tests; here we just want the value
        # returned by ``execute_child_workflow`` to flow through untouched.
        def _passthrough_rehydrate(pipe_output: Any, library_crate: Any) -> Any:
            del library_crate
            return pipe_output

        mocker.patch(
            "pipelex.temporal.tprl_pipe.temporal_pipe_router.rehydrate_pipe_output_with_crate",
            side_effect=_passthrough_rehydrate,
        )

        router = TemporalPipeRouter(task_queue="ut-test-queue")
        await router._run_pipe_job(pipe_job)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        kwargs = mock_execute_child.call_args.kwargs

        expected_details = build_static_details(pipe_job)
        expected_summary = build_static_summary(pipe_job.pipe)

        assert kwargs.get("static_details") == expected_details
        # Regression guard: don't allow static_details to become an empty
        # string or be silently dropped.
        assert kwargs.get("static_details")
        # Existing kwargs must still be present on the child dispatch.
        assert kwargs.get("static_summary") == expected_summary
        assert kwargs.get("search_attributes") is not None
        # Child workflow id is built as `{parent}_{pipe_code}-{8 hex}`.
        assert kwargs.get("id") == "ut-parent-wf-id_translate_doc-deadbeef"
