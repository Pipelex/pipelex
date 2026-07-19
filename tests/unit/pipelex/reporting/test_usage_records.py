import json

import pytest
from pytest_mock import MockerFixture

from pipelex.reporting.reporting_types import AnyTokensUsage
from pipelex.reporting.usage_records import (
    TokensUsageRecord,
    apply_tokens_usage_wire_shape,
    dump_tokens_usage_records,
    make_tokens_usage_record,
)
from tests.unit.pipelex.cogt.usage.test_data import RATED_EXPECTED_COST, UsageFixtures

WIRE_FIELDS = {
    "model_type",
    "inference_model_name",
    "inference_model_id",
    "pipe_code",
    "job_category",
    "unit_job_id",
    "nb_tokens_by_category",
    "cost",
    "started_at",
    "completed_at",
}

# The contract's MUST-NOT list: none of these may appear on a wire record, flat or nested.
MUST_NOT_FIELDS = [
    "job_metadata",
    "unit_costs",
    "user_id",
    "session_id",
    "request_id",
    "pipe_run_id",
    "otel_context",
    "trace_context",
    "content_generation_job_id",
    "pipeline_run_id",
]


class TestTokensUsageRecords:
    @pytest.mark.parametrize(
        ("tokens_usage", "expected_model_type", "expected_job_category", "expected_unit_job_id"),
        [
            (UsageFixtures.llm_usage(), "llm", "llm_job", "llm_gen_text"),
            (UsageFixtures.img_gen_usage(), "img_gen", "img_gen_job", "img_gen_text_to_image"),
            (UsageFixtures.extract_usage(), "extract", "extract_job", "extract_pages"),
            (UsageFixtures.search_usage(), "search", "search_job", "search_sourced_answer"),
        ],
        ids=["llm", "img_gen", "extract", "search"],
    )
    def test_conversion_per_variant(
        self,
        tokens_usage: AnyTokensUsage,
        expected_model_type: str,
        expected_job_category: str,
        expected_unit_job_id: str,
    ):
        """Every usage variant converts to the same single record shape, JobMetadata fields flattened."""
        record = make_tokens_usage_record(tokens_usage)
        assert record.model_type == expected_model_type
        assert record.inference_model_name == tokens_usage.inference_model_name
        assert record.inference_model_id == tokens_usage.inference_model_id
        assert record.pipe_code == "analyze_contract"
        assert record.job_category == expected_job_category
        assert record.unit_job_id == expected_unit_job_id
        assert record.nb_tokens_by_category == {"input": 1000, "input_cached": 400, "output": 250}
        assert record.cost == RATED_EXPECTED_COST
        assert record.started_at == "2026-07-19T10:00:00"
        assert record.completed_at == "2026-07-19T10:00:05"

    def test_cost_is_null_when_unrated(self):
        record = make_tokens_usage_record(UsageFixtures.unrated_usage())
        assert record.cost is None

    @pytest.mark.parametrize(
        "tokens_usage",
        [*UsageFixtures.all_variants(), UsageFixtures.unrated_usage()],
        ids=["llm", "img_gen", "extract", "search", "unrated"],
    )
    def test_leak_regression(self, tokens_usage: AnyTokensUsage):
        """The dumped wire record carries the contract fields exactly — none of the MUST-NOT
        internals (JobMetadata plumbing, rate table), flat or nested.
        """
        dumped = make_tokens_usage_record(tokens_usage).model_dump(mode="json")
        assert set(dumped.keys()) == WIRE_FIELDS
        dumped_text = json.dumps(dumped)
        for forbidden_field in MUST_NOT_FIELDS:
            assert forbidden_field not in dumped, f"MUST-NOT field '{forbidden_field}' leaked onto the wire record"
            assert f'"{forbidden_field}"' not in dumped_text, f"MUST-NOT field '{forbidden_field}' nested in the wire record"

    def test_dumped_record_is_json_safe_and_stringified(self):
        """Enums and timestamps dump as plain JSON strings — a consumer needs no runtime types."""
        dumped = make_tokens_usage_record(UsageFixtures.llm_usage()).model_dump(mode="json")
        reparsed = json.loads(json.dumps(dumped))
        assert reparsed["job_category"] == "llm_job"
        assert reparsed["unit_job_id"] == "llm_gen_text"
        assert reparsed["nb_tokens_by_category"] == {"input": 1000, "input_cached": 400, "output": 250}
        assert reparsed["started_at"] == "2026-07-19T10:00:00"
        # The record round-trips through its own model: the shape is closed (extra="forbid").
        assert TokensUsageRecord.model_validate(reparsed).model_dump(mode="json") == dumped

    def test_dump_null_and_empty_semantics(self):
        """None passes through (usage assembly off) and [] stays [] (on, no inference) — unchanged semantics."""
        assert dump_tokens_usage_records(None) is None
        assert dump_tokens_usage_records([]) == []

    def test_apply_wire_shape_replaces_execute_dump_records(self, mocker: MockerFixture):
        """The execute-response dump gets its full-fidelity usage dumps replaced by wire records."""
        tokens_usages = [UsageFixtures.llm_usage()]
        pipe_output = mocker.MagicMock()
        pipe_output.tokens_usages = tokens_usages
        response_dump = {
            "pipeline_run_id": "plr-fixture",
            "pipe_output": {
                "tokens_usages": [tokens_usage.model_dump(mode="json") for tokens_usage in tokens_usages],
                "usage_assembly_error": None,
            },
        }
        result = apply_tokens_usage_wire_shape(response_dump, pipe_output=pipe_output)
        assert result is response_dump
        records = result["pipe_output"]["tokens_usages"]
        assert len(records) == 1
        assert records[0]["model_type"] == "llm"
        assert records[0]["cost"] == RATED_EXPECTED_COST
        for forbidden_field in MUST_NOT_FIELDS:
            assert forbidden_field not in records[0]
        # The sibling diagnostic stays untouched (D5: bare string contract).
        assert result["pipe_output"]["usage_assembly_error"] is None

    def test_apply_wire_shape_preserves_none(self, mocker: MockerFixture):
        """A run with usage assembly off keeps tokens_usages null in the execute response."""
        pipe_output = mocker.MagicMock()
        pipe_output.tokens_usages = None
        response_dump = {"pipe_output": {"tokens_usages": None, "usage_assembly_error": None}}
        result = apply_tokens_usage_wire_shape(response_dump, pipe_output=pipe_output)
        assert result["pipe_output"]["tokens_usages"] is None
