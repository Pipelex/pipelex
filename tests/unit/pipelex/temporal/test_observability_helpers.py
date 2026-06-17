"""Unit tests for the observability helpers in ``pipelex.temporal.tprl.observability``.

The helpers build the Temporal observability surface (search attributes,
static summary/details, per-activity summary) from Pipelex identity. The
formatting policy is documented in
``wip/temporal-primitives/id-and-naming-design.md`` §"The four layers".
"""

from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.temporal.tprl.observability import (
    DOMAIN_CODE_KEY,
    PIPE_CODE_KEY,
    PIPELINE_RUN_ID_KEY,
    SESSION_ID_KEY,
    USER_ID_KEY,
    build_activity_summary,
    build_search_attributes,
    build_static_details,
    build_static_summary,
    stamp_submitter_session_id,
)

_STUB_SESSION_ID = "EdgdJ7Yk4Q3HF2pXyZv9w8"


def _make_pipe_job_stub(
    mocker: MockerFixture,
    *,
    pipe_code: str = "translate_doc",
    domain_code: str = "documents",
    description: str = "Translate a document from English to French",
    input_keys: list[str] | None = None,
    user_id: str = "acme-corp",
    pipeline_run_id: str = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
    session_id: str | None = _STUB_SESSION_ID,
    library_crate_fingerprint: str | None = None,
) -> Any:
    """Build a stub PipeJob with only the attributes the helpers read.

    ``session_id`` defaults to the canonical stub value because the helpers
    now read it directly off ``pipe_job.job_metadata`` instead of touching
    the worker-local ``TemporalManager``. Pass ``None`` to exercise the
    "session_id not stamped" fallback path.
    """
    pipe_job = mocker.MagicMock()
    pipe_job.pipe.code = pipe_code
    pipe_job.pipe.domain_code = domain_code
    pipe_job.pipe.description = description
    pipe_job.pipe.inputs.root = {key: object() for key in (input_keys or [])}
    pipe_job.job_metadata.user_id = user_id
    pipe_job.job_metadata.pipeline_run_id = pipeline_run_id
    pipe_job.job_metadata.session_id = session_id
    if library_crate_fingerprint is None:
        pipe_job.library_crate = None
    else:
        pipe_job.library_crate.fingerprint = library_crate_fingerprint
    return pipe_job


@pytest.fixture
def patch_temporal_manager(mocker: MockerFixture) -> None:
    """Patch ``get_temporal_manager`` so the ``stamp_submitter_session_id``
    helper can capture a value without needing a real ``TemporalManager``
    singleton. The observability helpers themselves no longer read it.
    """
    manager = mocker.MagicMock()
    manager.session_id = _STUB_SESSION_ID
    mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)


@pytest.fixture
def patch_search_attributes_config_all_enabled(mocker: MockerFixture) -> None:
    """Patch ``get_config`` so ``build_search_attributes`` sees the default
    "all five enabled" surface without booting Pipelex.
    """
    config_root = mocker.MagicMock()
    config_root.temporal.search_attributes.enabled = True
    config_root.temporal.search_attributes.attributes = ["PipeCode", "PipelineRunId", "SessionId", "UserId", "DomainCode"]
    mocker.patch("pipelex.temporal.tprl.observability.get_config", return_value=config_root)


@pytest.mark.usefixtures("patch_temporal_manager", "patch_search_attributes_config_all_enabled")
class TestObservabilityHelpers:
    def test_build_search_attributes_returns_five_typed_keys(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(mocker)

        attrs = build_search_attributes(pipe_job)

        assert attrs[PIPE_CODE_KEY] == "translate_doc"
        assert attrs[PIPELINE_RUN_ID_KEY] == "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"
        assert attrs[SESSION_ID_KEY] == "EdgdJ7Yk4Q3HF2pXyZv9w8"
        assert attrs[USER_ID_KEY] == "acme-corp"
        assert attrs[DOMAIN_CODE_KEY] == "documents"
        assert len(attrs) == 5

    def test_build_search_attributes_returns_empty_when_disabled(self, mocker: MockerFixture) -> None:
        """``enabled = false`` short-circuits to an empty ``TypedSearchAttributes``
        so the dashboard view degrades cleanly to WorkflowType / WorkflowId /
        StartTime without rejecting workflow starts.
        """
        config_root = mocker.MagicMock()
        config_root.temporal.search_attributes.enabled = False
        config_root.temporal.search_attributes.attributes = []
        mocker.patch("pipelex.temporal.tprl.observability.get_config", return_value=config_root)
        pipe_job = _make_pipe_job_stub(mocker)

        attrs = build_search_attributes(pipe_job)

        assert len(attrs) == 0

    def test_build_search_attributes_reads_session_id_from_pipe_job_not_manager(self, mocker: MockerFixture) -> None:
        """Determinism regression: ``build_search_attributes`` must be a pure
        function of ``pipe_job``. Reading ``TemporalManager.session_id`` from
        inside workflow code produced non-deterministic ``StartChildWorkflowExecution``
        commands on replay across worker restarts. Two ``pipe_job`` stubs with
        the same stamped ``job_metadata.session_id`` but different fake
        managers must yield byte-equal ``SessionId`` pairs.
        """
        manager_alpha = mocker.MagicMock()
        manager_alpha.session_id = "this-must-not-leak-into-attrs-A"
        mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager_alpha)
        pipe_job = _make_pipe_job_stub(mocker, session_id="stamped-at-submitter")

        attrs_first = build_search_attributes(pipe_job)

        manager_beta = mocker.MagicMock()
        manager_beta.session_id = "this-must-not-leak-into-attrs-B"
        mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager_beta)

        attrs_second = build_search_attributes(pipe_job)

        assert attrs_first[SESSION_ID_KEY] == "stamped-at-submitter"
        assert attrs_second[SESSION_ID_KEY] == "stamped-at-submitter"

    def test_build_search_attributes_filters_to_configured_subset(self, mocker: MockerFixture) -> None:
        """When ``attributes`` lists only a subset of the five built-ins, only
        those pairs end up on the workflow start.
        """
        config_root = mocker.MagicMock()
        config_root.temporal.search_attributes.enabled = True
        config_root.temporal.search_attributes.attributes = ["PipeCode", "DomainCode"]
        mocker.patch("pipelex.temporal.tprl.observability.get_config", return_value=config_root)
        pipe_job = _make_pipe_job_stub(mocker)

        attrs = build_search_attributes(pipe_job)

        assert len(attrs) == 2
        assert attrs[PIPE_CODE_KEY] == "translate_doc"
        assert attrs[DOMAIN_CODE_KEY] == "documents"

    def test_build_static_summary_with_description(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(mocker)

        summary = build_static_summary(pipe_job.pipe)

        assert summary == "translate_doc — Translate a document from English to French"

    def test_build_static_summary_with_empty_description_omits_dash_tail(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(mocker, description="")

        summary = build_static_summary(pipe_job.pipe)

        assert summary == "translate_doc"

    def test_build_static_summary_truncates_at_200_bytes_with_ellipsis(self, mocker: MockerFixture) -> None:
        long_description = "x" * 300
        pipe_job = _make_pipe_job_stub(mocker, description=long_description)

        summary = build_static_summary(pipe_job.pipe)

        assert len(summary.encode("utf-8")) <= 200
        assert summary.endswith("…")

    def test_build_static_summary_truncates_utf8_safely_at_multibyte_boundary(self, mocker: MockerFixture) -> None:
        # Use 3-byte UTF-8 characters (CJK) to force a partial sequence near the cut.
        long_description = "漢" * 100
        pipe_job = _make_pipe_job_stub(mocker, description=long_description)

        summary = build_static_summary(pipe_job.pipe)

        # Decoding the result must not raise UnicodeDecodeError — i.e. the
        # truncation correctly drops any partial multi-byte sequence at the cut.
        summary.encode("utf-8").decode("utf-8")
        assert summary.endswith("…")
        assert len(summary.encode("utf-8")) <= 200

    def test_build_static_details_includes_all_required_rows(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(
            mocker,
            input_keys=["source_text", "target_language"],
            library_crate_fingerprint="abcdef0123456789deadbeefcafebabe1234567890",
        )

        details = build_static_details(pipe_job)

        assert "| Pipe | `translate_doc` |" in details
        assert "| Domain | `documents` |" in details
        assert "| Pipeline run | `3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c` |" in details
        assert "| User | `acme-corp` |" in details
        assert "| Session | `EdgdJ7Yk4Q3HF2pXyZv9w8` |" in details
        # Library crate fingerprint is truncated to 12 chars.
        assert "| Library crate | `abcdef012345` |" in details
        assert "| Input | `source_text`, `target_language` |" in details

    def test_build_static_details_omits_optional_rows_when_unavailable(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(mocker, input_keys=[])

        details = build_static_details(pipe_job)

        assert "Library crate" not in details
        assert "Input" not in details
        # Core identity rows still present.
        assert "| Pipe | `translate_doc` |" in details
        assert "| Pipeline run |" in details

    def test_build_static_details_omits_library_crate_when_fingerprint_is_empty(self, mocker: MockerFixture) -> None:
        """A LibraryCrate whose fingerprint has not been computed must not produce a row."""
        pipe_job = _make_pipe_job_stub(mocker, library_crate_fingerprint="")

        details = build_static_details(pipe_job)

        assert "Library crate" not in details

    def test_stamp_submitter_session_id_sets_when_missing(self, mocker: MockerFixture) -> None:
        """At top-level dispatch, the helper must read ``TemporalManager.session_id``
        once and write it onto ``pipe_job.job_metadata`` so the value flows into
        child workflows via the workflow input.
        """
        manager = mocker.MagicMock()
        manager.session_id = "submitter-session-xyz"
        mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)

        pipe_job = _make_pipe_job_stub(mocker, session_id=None)
        # Configure the model_copy chain so the assertion sees the stamped value.
        updated_metadata = mocker.MagicMock()
        updated_metadata.session_id = "submitter-session-xyz"
        pipe_job.job_metadata.model_copy.return_value = updated_metadata
        stamped_pipe_job = mocker.MagicMock()
        stamped_pipe_job.job_metadata = updated_metadata
        pipe_job.model_copy.return_value = stamped_pipe_job

        stamped = stamp_submitter_session_id(pipe_job)

        assert stamped.job_metadata.session_id == "submitter-session-xyz"
        # The helper must call model_copy with the right update payload.
        pipe_job.job_metadata.model_copy.assert_called_once_with(update={"session_id": "submitter-session-xyz"})
        pipe_job.model_copy.assert_called_once_with(update={"job_metadata": updated_metadata})

    def test_stamp_submitter_session_id_is_idempotent(self, mocker: MockerFixture) -> None:
        """When ``session_id`` is already set on the incoming ``pipe_job``,
        the helper must return the same object untouched — child workflows
        inherit the parent's session_id and must not have it overwritten by
        a worker-local fallback.
        """
        manager = mocker.MagicMock()
        manager.session_id = "worker-local-value-should-be-ignored"
        mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)
        pipe_job = _make_pipe_job_stub(mocker, session_id="parent-session-preserved")

        stamped = stamp_submitter_session_id(pipe_job)

        assert stamped is pipe_job
        assert stamped.job_metadata.session_id == "parent-session-preserved"
        pipe_job.job_metadata.model_copy.assert_not_called()
        pipe_job.model_copy.assert_not_called()

    def test_build_search_attributes_falls_back_to_empty_string_when_session_unset(self, mocker: MockerFixture) -> None:
        """Defensive fallback: if a caller bypasses ``stamp_submitter_session_id``
        somehow, ``build_search_attributes`` must emit an empty string for
        ``SessionId`` rather than ``None`` (Keyword attributes reject ``None``).
        """
        pipe_job = _make_pipe_job_stub(mocker, session_id=None)

        attrs = build_search_attributes(pipe_job)

        assert attrs[SESSION_ID_KEY] == ""

    def test_build_static_details_truncates_at_20kb(self, mocker: MockerFixture) -> None:
        """Module docstring claims ``static_details`` are capped at 20 KB.
        Push the input list past the cap and assert the renderer truncates
        with an ellipsis instead of returning an oversize payload.
        """
        long_input_names = [f"input_field_name_{index:04d}" for index in range(2000)]
        pipe_job = _make_pipe_job_stub(mocker, input_keys=long_input_names)

        details = build_static_details(pipe_job)

        assert len(details.encode("utf-8")) <= 20 * 1024
        assert details.endswith("…")

    def test_build_activity_summary_includes_method_pipe_and_extras(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="translate_doc")

        summary = build_activity_summary("LLM text", job_metadata=job_metadata, extras={"model": "gpt-4o"})

        assert summary == "LLM text · pipe=translate_doc · model=gpt-4o"

    def test_build_activity_summary_accepts_reserved_word_keys(self) -> None:
        """``class`` is a Python reserved word — the design table specifies
        ``class={class_name}`` verbatim, and the ``extras`` mapping (vs ``**kwargs``)
        lets callers use it as a key without contortions.
        """
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="extract_text")

        summary = build_activity_summary("LLM object", job_metadata=job_metadata, extras={"class": "Section"})

        assert summary == "LLM object · pipe=extract_text · class=Section"

    def test_build_activity_summary_omits_pipe_segment_when_pipe_code_is_unset(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r")

        summary = build_activity_summary("LLM text", job_metadata=job_metadata, extras={"model": "gpt-4o"})

        assert summary == "LLM text · model=gpt-4o"

    def test_build_activity_summary_omits_extras_section_when_none(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="my_pipe")

        summary = build_activity_summary("Templated text", job_metadata=job_metadata)

        assert summary == "Templated text · pipe=my_pipe"

    def test_build_activity_summary_truncates_at_200_bytes(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="p")
        long_value = "x" * 500

        summary = build_activity_summary("LLM text", job_metadata=job_metadata, extras={"extra": long_value})

        assert len(summary.encode("utf-8")) <= 200
        assert summary.endswith("…")
