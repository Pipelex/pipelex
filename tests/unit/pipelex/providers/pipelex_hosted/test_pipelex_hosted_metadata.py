"""The `x-pipelex-metadata` value: its exact shape, who wins a collision, and why it cannot forge a line.

The header is how The Pipelex service attributes spend and logs a call, so its value is asserted as
the wire string. The collision rule is the security-relevant one: `extras` is caller data whose key
charset admits every one of the runtime's key names, so a label named `user_id` must never restate
the run's identity to the service that bills for it.
"""

from __future__ import annotations

import json

import pytest

from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PIPELEX_HOSTED_AUTH_HEADER, PIPELEX_HOSTED_METADATA_HEADER
from pipelex.providers.pipelex_hosted.pipelex_hosted_metadata import (
    encode_pipelex_hosted_metadata,
    make_pipelex_hosted_metadata,
    make_pipelex_hosted_metadata_headers,
)
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.run_extras import RUN_EXTRAS_KEY_PATTERN
from tests.unit.pipelex.providers.pipelex_hosted.test_data import PipelexHostedMetadataTestData

_RUNTIME_KEYS = ("user_id", "pipeline_run_id", "pipe_run_id", "pipe_code", "content_generation_job_id")


def _job_metadata(
    *,
    extras: dict[str, str] | None = None,
    user_id: str = "user_42",
    pipe_code: str | None = None,
    pipe_run_id: str | None = None,
    content_generation_job_id: str | None = None,
) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(
            storage_scope="test/scope",
            read_scope=None,
            user_id=user_id,
            pipeline_run_id="run_abc",
            extras=extras or {},
        ),
        pipe_code=pipe_code,
        pipe_run_id=pipe_run_id,
        content_generation_job_id=content_generation_job_id,
    )


class TestPipelexHostedMetadata:
    def test_the_header_is_named_by_the_dialect_and_never_by_the_vendor(self) -> None:
        assert PIPELEX_HOSTED_METADATA_HEADER == "x-pipelex-metadata"
        assert PIPELEX_HOSTED_METADATA_HEADER != PIPELEX_HOSTED_AUTH_HEADER

    def test_a_job_with_extras_yields_the_exact_wire_value(self) -> None:
        headers = make_pipelex_hosted_metadata_headers(job_metadata=PipelexHostedMetadataTestData.JOB_METADATA)

        assert headers == {PIPELEX_HOSTED_METADATA_HEADER: PipelexHostedMetadataTestData.EXPECTED_HEADER_VALUE}
        decoded = json.loads(headers[PIPELEX_HOSTED_METADATA_HEADER])
        assert decoded == {
            "org_id": "org_acme",
            "api_key_id": "key_123",
            "user_id": "user_42",
            "pipeline_run_id": "run_abc",
            "pipe_run_id": "0123456789abcdef",
            "pipe_code": "summarize_doc",
            "content_generation_job_id": "cgj_1",
        }

    def test_every_runtime_key_is_a_legal_extras_key_so_a_collision_is_possible(self) -> None:
        """The premise of the collision rule: the extras charset does not keep these names out."""
        for runtime_key in _RUNTIME_KEYS:
            assert RUN_EXTRAS_KEY_PATTERN.fullmatch(runtime_key), runtime_key

    def test_the_runtime_ids_win_over_colliding_extras_keys(self) -> None:
        job_metadata = _job_metadata(
            extras={"user_id": "spoofed_user", "pipeline_run_id": "spoofed_run", "org_id": "org_acme"},
            pipe_code="real_pipe",
            pipe_run_id="real_pipe_run",
            content_generation_job_id="real_cgj",
        )

        metadata = make_pipelex_hosted_metadata(job_metadata=job_metadata)

        assert metadata == {
            "org_id": "org_acme",
            "user_id": "user_42",
            "pipeline_run_id": "run_abc",
            "pipe_run_id": "real_pipe_run",
            "pipe_code": "real_pipe",
            "content_generation_job_id": "real_cgj",
        }

    def test_a_none_id_is_omitted_and_a_colliding_extras_key_does_not_stand_in_for_it(self) -> None:
        """An id the job lacks is absent, never `null`, and never filled by the caller's label of that name."""
        job_metadata = _job_metadata(extras={"pipe_code": "spoofed_pipe", "org_id": "org_acme"})

        metadata = make_pipelex_hosted_metadata(job_metadata=job_metadata)

        assert metadata == {"org_id": "org_acme", "user_id": "user_42", "pipeline_run_id": "run_abc"}
        assert "null" not in make_pipelex_hosted_metadata_headers(job_metadata=job_metadata)[PIPELEX_HOSTED_METADATA_HEADER]

    def test_empty_extras_yield_the_runtime_ids_alone(self) -> None:
        headers = make_pipelex_hosted_metadata_headers(job_metadata=_job_metadata(pipe_code="p", pipe_run_id="r"))

        assert headers == {PIPELEX_HOSTED_METADATA_HEADER: '{"user_id":"user_42","pipeline_run_id":"run_abc","pipe_run_id":"r","pipe_code":"p"}'}

    @pytest.mark.parametrize(
        "hostile_user_id",
        ["user\r\nx-injected: 1", "user\nforged", "café-☃", "del\x7fchar", "tab\there"],
        ids=["crlf", "lf", "non-ascii", "del", "tab"],
    )
    def test_the_value_is_printable_ascii_whatever_went_in(self, hostile_user_id: str) -> None:
        """`user_id` has no charset of its own, so the encoding is what keeps the header one line."""
        value = make_pipelex_hosted_metadata_headers(job_metadata=_job_metadata(user_id=hostile_user_id))[PIPELEX_HOSTED_METADATA_HEADER]

        assert all(0x20 <= ord(char) <= 0x7E for char in value), value
        assert json.loads(value)["user_id"] == hostile_user_id

    def test_the_encoding_is_compact_json(self) -> None:
        assert encode_pipelex_hosted_metadata(metadata={"a": "1", "b": "2"}) == '{"a":"1","b":"2"}'
