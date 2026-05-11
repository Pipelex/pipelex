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
    build_activity_summary,
    build_search_attributes,
    build_static_details,
    build_static_summary,
)


def _make_pipe_job_stub(
    mocker: MockerFixture,
    *,
    pipe_code: str = "translate_doc",
    domain_code: str = "documents",
    description: str = "Translate a document from English to French",
    input_keys: list[str] | None = None,
    user_id: str = "acme-corp",
    pipeline_run_id: str = "3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c",
    library_crate_fingerprint: str | None = None,
) -> Any:
    """Build a stub PipeJob with only the attributes the helpers read."""
    pipe_job = mocker.MagicMock()
    pipe_job.pipe.code = pipe_code
    pipe_job.pipe.domain_code = domain_code
    pipe_job.pipe.description = description
    pipe_job.pipe.inputs.root = {key: object() for key in (input_keys or [])}
    pipe_job.job_metadata.user_id = user_id
    pipe_job.job_metadata.pipeline_run_id = pipeline_run_id
    if library_crate_fingerprint is None:
        pipe_job.library_crate = None
    else:
        pipe_job.library_crate.fingerprint = library_crate_fingerprint
    return pipe_job


@pytest.fixture
def patch_temporal_manager(mocker: MockerFixture) -> None:
    """Patch ``get_temporal_manager`` so the helpers can read ``session_id``
    without needing a real ``TemporalManager`` singleton.
    """
    manager = mocker.MagicMock()
    manager.session_id = "EdgdJ7Yk4Q3HF2pXyZv9w8"
    mocker.patch("pipelex.temporal.tprl.observability.get_temporal_manager", return_value=manager)


@pytest.mark.usefixtures("patch_temporal_manager")
class TestObservabilityHelpers:
    def test_build_search_attributes_returns_five_keyed_dict(self, mocker: MockerFixture) -> None:
        pipe_job = _make_pipe_job_stub(mocker)

        attrs = build_search_attributes(pipe_job)

        assert dict(attrs) == {
            "PipeCode": ["translate_doc"],
            "PipelineRunId": ["3f9c8b2a-1e4d-4f5b-9c7a-2d8e1f0a6b3c"],
            "SessionId": ["EdgdJ7Yk4Q3HF2pXyZv9w8"],
            "UserId": ["acme-corp"],
            "DomainCode": ["documents"],
        }

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

    def test_build_activity_summary_includes_method_pipe_and_extras(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="translate_doc")

        summary = build_activity_summary("LLM text", job_metadata, extras={"model": "gpt-4o"})

        assert summary == "LLM text · pipe=translate_doc · model=gpt-4o"

    def test_build_activity_summary_accepts_reserved_word_keys(self) -> None:
        """``class`` is a Python reserved word — the design table specifies
        ``class={class_name}`` verbatim, and the ``extras`` mapping (vs ``**kwargs``)
        lets callers use it as a key without contortions.
        """
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="extract_text")

        summary = build_activity_summary("LLM object", job_metadata, extras={"class": "Section"})

        assert summary == "LLM object · pipe=extract_text · class=Section"

    def test_build_activity_summary_omits_pipe_segment_when_pipe_code_is_unset(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r")

        summary = build_activity_summary("LLM text", job_metadata, extras={"model": "gpt-4o"})

        assert summary == "LLM text · model=gpt-4o"

    def test_build_activity_summary_omits_extras_section_when_none(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="my_pipe")

        summary = build_activity_summary("Templated text", job_metadata)

        assert summary == "Templated text · pipe=my_pipe"

    def test_build_activity_summary_truncates_at_200_bytes(self) -> None:
        job_metadata = JobMetadata(user_id="u", pipeline_run_id="r", pipe_code="p")
        long_value = "x" * 500

        summary = build_activity_summary("LLM text", job_metadata, extras={"extra": long_value})

        assert len(summary.encode("utf-8")) <= 200
        assert summary.endswith("…")
