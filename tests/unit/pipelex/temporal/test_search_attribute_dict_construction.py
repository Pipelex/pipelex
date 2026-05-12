"""Unit tests for the five-keyed typed search attributes.

Pins the schema documented in
``wip/temporal-primitives/id-and-naming-design.md`` §"Layer 4 — Search & Filter":

| Attribute      | Source                                          |
|----------------|-------------------------------------------------|
| PipeCode       | pipe_job.pipe.code                              |
| PipelineRunId  | pipe_job.job_metadata.pipeline_run_id           |
| SessionId      | pipe_job.job_metadata.session_id (stamped       |
|                | from TemporalManager at submitter dispatch)     |
| UserId         | pipe_job.job_metadata.user_id                   |
| DomainCode     | pipe_job.pipe.domain_code                       |

Every value flows off ``pipe_job`` — the helper is a pure function of the
workflow input. ``SessionId`` is read directly from ``TemporalManager`` only
once, by ``stamp_submitter_session_id`` at the top-level dispatch boundary;
inside workflow code the value comes through ``job_metadata`` unchanged so
``StartChildWorkflowExecution`` commands stay byte-equal across replays even
when the worker process restarts.

Child workflows reuse the same builder against the child's own ``pipe_job``:
``PipelineRunId`` / ``UserId`` / ``SessionId`` are inherited from the parent
via ``pipe_job.job_metadata`` (propagated as workflow input), and ``PipeCode`` /
``DomainCode`` naturally reflect the child's pipe.
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.temporal.tprl.observability import (
    DOMAIN_CODE_KEY,
    PIPE_CODE_KEY,
    PIPELINE_RUN_ID_KEY,
    SESSION_ID_KEY,
    USER_ID_KEY,
    build_search_attributes,
)


def _make_pipe_job_stub(
    mocker: MockerFixture,
    *,
    pipe_code: str,
    domain_code: str,
    user_id: str = "acme-corp",
    pipeline_run_id: str = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
    session_id: str = "EdgdJ7Yk4Q3HF2pXyZv9w8",
) -> Any:
    pipe_job = mocker.MagicMock()
    pipe_job.pipe.code = pipe_code
    pipe_job.pipe.domain_code = domain_code
    pipe_job.job_metadata.user_id = user_id
    pipe_job.job_metadata.pipeline_run_id = pipeline_run_id
    pipe_job.job_metadata.session_id = session_id
    return pipe_job


@pytest.fixture
def patch_search_attributes_config_all_enabled(mocker: MockerFixture) -> None:
    """Patch ``get_config`` so ``build_search_attributes`` sees the default
    "all five enabled" surface without booting Pipelex.
    """
    config_root = mocker.MagicMock()
    config_root.temporal.search_attributes.enabled = True
    config_root.temporal.search_attributes.attributes = ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
    mocker.patch("pipelex.temporal.tprl.observability.get_config", return_value=config_root)


@pytest.mark.usefixtures("patch_search_attributes_config_all_enabled")
class TestSearchAttributeDictConstruction:
    def test_top_level_attrs_have_five_keys_with_correct_value_sources(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(
            mocker,
            pipe_code="translate_doc",
            domain_code="documents",
            user_id="acme-corp",
            pipeline_run_id="3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
        )

        attrs = build_search_attributes(pipe_job)

        assert len(attrs) == 5
        assert attrs[PIPE_CODE_KEY] == "translate_doc"
        assert attrs[PIPELINE_RUN_ID_KEY] == "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
        assert attrs[SESSION_ID_KEY] == "EdgdJ7Yk4Q3HF2pXyZv9w8"
        assert attrs[USER_ID_KEY] == "acme-corp"
        assert attrs[DOMAIN_CODE_KEY] == "documents"

    def test_child_pipe_job_carries_inherited_identity_and_own_pipe_code(self, mocker: MockerFixture) -> None:
        """Child workflows reuse ``build_search_attributes`` on the child's own
        ``pipe_job``. ``PipeCode`` / ``DomainCode`` reflect the child's pipe;
        ``PipelineRunId`` / ``UserId`` / ``SessionId`` are inherited from the
        parent because the child's ``job_metadata`` is propagated as workflow
        input from the parent — including the ``SessionId`` stamped at the
        submitter dispatch boundary, which keeps the start-child-workflow
        command deterministic across replays.
        """
        child_pipe_job = _make_pipe_job_stub(
            mocker,
            pipe_code="extract_text",
            domain_code="extraction",
            pipeline_run_id="parent-run-id",
            user_id="parent-user",
            session_id="parent-session",
        )

        child_attrs = build_search_attributes(child_pipe_job)

        # Child's own:
        assert child_attrs[PIPE_CODE_KEY] == "extract_text"
        assert child_attrs[DOMAIN_CODE_KEY] == "extraction"
        # Inherited via propagated job_metadata:
        assert child_attrs[PIPELINE_RUN_ID_KEY] == "parent-run-id"
        assert child_attrs[USER_ID_KEY] == "parent-user"
        assert child_attrs[SESSION_ID_KEY] == "parent-session"
