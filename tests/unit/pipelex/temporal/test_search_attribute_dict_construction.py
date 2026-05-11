"""Unit tests for the five-keyed search-attribute dict.

Pins the schema documented in
``wip/temporal-primitives/id-and-naming-design.md`` §"Layer 4 — Search & Filter":

| Attribute      | Source                                          |
|----------------|-------------------------------------------------|
| PipeCode       | pipe_job.pipe.code                              |
| PipelineRunId  | pipe_job.job_metadata.pipeline_run_id           |
| SessionId      | TemporalManager.get_instance().session_id       |
| UserId         | pipe_job.job_metadata.user_id                   |
| DomainCode     | pipe_job.pipe.domain_code                       |

Child workflows reuse the same builder against the child's own ``pipe_job``:
``PipelineRunId`` / ``UserId`` are inherited from the parent via
``pipe_job.job_metadata`` (propagated as workflow input), and ``PipeCode`` /
``DomainCode`` naturally reflect the child's pipe.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.temporal.tprl.observability import build_search_attributes


def _make_pipe_job_stub(
    mocker: MockerFixture,
    *,
    pipe_code: str,
    domain_code: str,
    user_id: str = "acme-corp",
    pipeline_run_id: str = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
) -> Any:
    pipe_job = mocker.MagicMock()
    pipe_job.pipe.code = pipe_code
    pipe_job.pipe.domain_code = domain_code
    pipe_job.job_metadata.user_id = user_id
    pipe_job.job_metadata.pipeline_run_id = pipeline_run_id
    return pipe_job


@pytest.fixture
def patch_temporal_manager(mocker: MockerFixture) -> None:
    """Patch ``get_temporal_manager`` so the helpers can read ``session_id``
    without setting up the real singleton.
    """
    manager = mocker.MagicMock()
    manager.session_id = "EdgdJ7Yk4Q3HF2pXyZv9w8"
    mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)


@pytest.mark.usefixtures("patch_temporal_manager")
class TestSearchAttributeDictConstruction:
    def test_top_level_dict_has_five_keys_with_correct_value_sources(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(
            mocker,
            pipe_code="translate_doc",
            domain_code="documents",
            user_id="acme-corp",
            pipeline_run_id="3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
        )

        attrs = build_search_attributes(pipe_job)

        assert sorted(attrs.keys()) == sorted(["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"])
        assert attrs["PipeCode"] == ["translate_doc"]
        assert attrs["PipelineRunId"] == ["3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"]
        assert attrs["SessionId"] == ["EdgdJ7Yk4Q3HF2pXyZv9w8"]
        assert attrs["UserId"] == ["acme-corp"]
        assert attrs["DomainCode"] == ["documents"]

    def test_child_pipe_job_carries_inherited_identity_and_own_pipe_code(self, mocker: MockerFixture) -> None:
        """Child workflows reuse ``build_search_attributes`` on the child's own
        ``pipe_job``. ``PipeCode`` / ``DomainCode`` reflect the child's pipe;
        ``PipelineRunId`` / ``UserId`` are inherited from the parent because the
        child's ``job_metadata`` is propagated as workflow input from the parent.
        ``SessionId`` is read from ``TemporalManager`` on whichever side runs the
        builder (submitter for top-level, worker for child).
        """
        child_pipe_job = _make_pipe_job_stub(
            mocker,
            pipe_code="extract_text",
            domain_code="extraction",
            pipeline_run_id="parent-run-id",
            user_id="parent-user",
        )

        child_attrs = build_search_attributes(child_pipe_job)

        # Child's own:
        assert child_attrs["PipeCode"] == ["extract_text"]
        assert child_attrs["DomainCode"] == ["extraction"]
        # Inherited via propagated job_metadata:
        assert child_attrs["PipelineRunId"] == ["parent-run-id"]
        assert child_attrs["UserId"] == ["parent-user"]
        # From TemporalManager:
        assert child_attrs["SessionId"] == ["EdgdJ7Yk4Q3HF2pXyZv9w8"]
