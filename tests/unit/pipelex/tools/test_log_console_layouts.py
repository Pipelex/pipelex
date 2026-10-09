from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.tools.log.console_fields import FIELD_STYLES, FIELD_VALUE_MAX_LENGTH
from pipelex.tools.log.console_layouts import CONSOLE_LAYOUTS, PIPE_RUN_MAX_DEPTH, ConsoleLayout, LogLayout, PipeRunLayout
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_fields import FIELD_NAMES_MARK, LAYOUT_MARK
from pipelex.tools.log.log_redaction import QUARANTINE_PREFIX, REDACTED_TEXT
from tests.helpers.console_log_rendering import (
    PIPE_RUN_FIELDS,
    console_sink_on_buffer,
    installed_log,
    record_with_fields,
    rendered_text,
    styles_of,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

# The fields of the event an inference call ends with, for a call that reported its usage and its cost.
INFERENCE_CALL_END_FIELDS: dict[str, Any] = {
    "gen_ai.operation.name": "chat",
    "model_handle": "gpt-5.6-terra",
    "backend_name": "openai",
    "sdk": "openai_responses",
    "gen_ai.request.model": "gpt-5.6-terra",
    "gen_ai.response.model": "gpt-5.6-terra-2026-08-01",
    "gen_ai.usage.input_tokens": 12288,
    "gen_ai.usage.output_tokens": 567,
    "cost_usd": 0.0123,
    "duration_ms": 1234.5,
    "outcome": "success",
}
# The fields of the event a pipe run ends with, for a top-level run that succeeded.
PIPE_RUN_END_FIELDS: dict[str, Any] = {**PIPE_RUN_FIELDS, "duration_ms": 840.0, "outcome": "success"}
USAGE_KEYS = ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens", "cost_usd")


class TestConsoleLayouts:
    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, "PipeCompose: compose_company → Company"),
            ({"pipe_depth": 1}, "   ↳ PipeCompose: compose_company → Company"),
            ({"pipe_depth": 2}, "      ↳ PipeCompose: compose_company → Company"),
        ],
        ids=["top level", "nested", "nested twice"],
    )
    def test_the_pipe_run_layout_draws_the_tree_in_the_style_map_colours(self, overrides: dict[str, Any], expected: str) -> None:
        text = rendered_text(record=record_with_fields(message="Pipe run starts", extra={**PIPE_RUN_FIELDS, **overrides}, layout=LogLayout.PIPE_RUN))

        assert text.plain == f"🧠: {expected}"
        assert styles_of(text=text, fragment="compose_company") == [FIELD_STYLES["pipe_code"]]
        assert styles_of(text=text, fragment="Company") == [FIELD_STYLES["output_concept"]]

    @pytest.mark.parametrize(
        ("overrides", "dropped", "expected"),
        [
            ({}, (), "gpt-5.6-terra chat · 12,288 → 567 tokens · $0.0123 · done in 1.23 s"),
            ({"duration_ms": 840.4}, (), "gpt-5.6-terra chat · 12,288 → 567 tokens · $0.0123 · done in 840 ms"),
            ({"duration_ms": 999.6}, (), "gpt-5.6-terra chat · 12,288 → 567 tokens · $0.0123 · done in 1.00 s"),
            ({}, ("gen_ai.usage.output_tokens",), "gpt-5.6-terra chat · 12,288 tokens in · $0.0123 · done in 1.23 s"),
            ({}, ("gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens"), "gpt-5.6-terra chat · $0.0123 · done in 1.23 s"),
            ({}, ("cost_usd",), "gpt-5.6-terra chat · 12,288 → 567 tokens · done in 1.23 s"),
            ({"gen_ai.operation.name": "doc_gen", "model_handle": "reportlab-pdf"}, USAGE_KEYS, "reportlab-pdf doc_gen · done in 1.23 s"),
            ({"cost_usd": 0.0}, (), "gpt-5.6-terra chat · 12,288 → 567 tokens · $0 · done in 1.23 s"),
            (
                {"outcome": "error", "error.type": "LLMCompletionError"},
                USAGE_KEYS,
                "gpt-5.6-terra chat · failed after 1.23 s error.type=LLMCompletionError",
            ),
        ],
        ids=[
            "tokens and cost",
            "under a second",
            "a second once rounded",
            "tokens in alone",
            "a cost alone",
            "tokens alone",
            "no usage at all",
            "a free call",
            "a failure",
        ],
    )
    def test_the_inference_call_end_layout_draws_the_call_on_one_compact_line(
        self, overrides: dict[str, Any], dropped: tuple[str, ...], expected: str
    ) -> None:
        fields = {key: value for key, value in {**INFERENCE_CALL_END_FIELDS, **overrides}.items() if key not in dropped}

        text = rendered_text(record=record_with_fields(message="Inference call ends", extra=fields, layout=LogLayout.INFERENCE_CALL_END))

        assert text.plain == f"🧠: {expected}"

    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, "EndingPipe: compose_company done in 840 ms"),
            ({"pipe_depth": 2, "duration_ms": 61_250.0}, "      ↳ EndingPipe: compose_company done in 61.25 s"),
            ({"outcome": "error", "error.type": "PipeRunError"}, "EndingPipe: compose_company failed after 840 ms error.type=PipeRunError"),
        ],
        ids=["top level", "nested twice", "a failure"],
    )
    def test_the_pipe_run_end_layout_draws_the_end_in_the_pipe_tree(self, overrides: dict[str, Any], expected: str) -> None:
        fields = {**PIPE_RUN_END_FIELDS, "pipe_type": "EndingPipe", **overrides}

        text = rendered_text(record=record_with_fields(message="Pipe run ends", extra=fields, layout=LogLayout.PIPE_RUN_END))

        assert text.plain == f"🧠: {expected}"
        assert styles_of(text=text, fragment="compose_company") == [FIELD_STYLES["pipe_code"]]

    @pytest.mark.parametrize(
        ("layout", "fields", "overrides", "expected_values"),
        [
            (LogLayout.PIPE_RUN_END, PIPE_RUN_END_FIELDS, {"outcome": "partial"}, "outcome=partial"),
            (LogLayout.PIPE_RUN_END, PIPE_RUN_END_FIELDS, {"duration_ms": -1.0}, "duration_ms=-1.0"),
            (LogLayout.PIPE_RUN_END, PIPE_RUN_END_FIELDS, {"duration_ms": "slow"}, "duration_ms=slow"),
            (LogLayout.INFERENCE_CALL_END, INFERENCE_CALL_END_FIELDS, {"cost_usd": "cheap"}, "cost_usd=cheap"),
            (LogLayout.INFERENCE_CALL_END, INFERENCE_CALL_END_FIELDS, {"gen_ai.usage.input_tokens": 1.5}, "gen_ai.usage.input_tokens=1.5"),
        ],
        ids=["an unknown outcome", "a negative duration", "a duration that is no number", "a cost that is no number", "a fractional token count"],
    )
    def test_a_value_a_summary_layout_refuses_falls_back_to_the_message_and_every_field(
        self, layout: LogLayout, fields: dict[str, Any], overrides: dict[str, Any], expected_values: str
    ) -> None:
        text = rendered_text(record=record_with_fields(message="Work ends", extra={**fields, **overrides}, layout=layout))

        assert text.plain.startswith("🧠: Work ends ")
        assert expected_values in text.plain

    def test_a_value_carrying_markup_or_an_emoji_code_prints_as_written_inside_a_layout(self) -> None:
        record = record_with_fields(
            message="Pipe run starts",
            extra={**PIPE_RUN_FIELDS, "pipe_code": "[red]x[/red]", "output_concept": ":fire:"},
            layout=LogLayout.PIPE_RUN,
        )

        text = rendered_text(record=record)

        assert text.plain == "🧠: PipeCompose: [red]x[/red] → :fire:"
        assert styles_of(text=text, fragment="[red]x[/red]") == [FIELD_STYLES["pipe_code"]]

    def test_the_console_renders_a_layout_end_to_end_and_the_other_fields_follow_it(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh, fresh.context(request_id="req-1"):
            fresh.info("Pipe run starts", fields={**PIPE_RUN_FIELDS, "pipe_depth": 1, "attempt": 2}, layout=LogLayout.PIPE_RUN)

        rendered = buffer.getvalue()
        assert "   ↳ PipeCompose: compose_company → Company attempt=2" in rendered
        assert "Pipe run starts" not in rendered
        assert "req-1" not in rendered

    @pytest.mark.parametrize(
        ("overrides", "expected_values"),
        [
            ({"pipe_depth": "deep"}, "pipe_depth=deep"),
            ({"pipe_depth": 10**20}, "pipe_depth=100000000000000000000"),
            ({"pipe_depth": PIPE_RUN_MAX_DEPTH + 1}, f"pipe_depth={PIPE_RUN_MAX_DEPTH + 1}"),
            ({"pipe_depth": -1}, "pipe_depth=-1"),
            ({"pipe_depth": True}, "pipe_depth=true"),
        ],
        ids=[
            "a depth that is no integer",
            "a depth no index can hold",
            "a depth past the bound",
            "a negative depth",
            "a boolean depth",
        ],
    )
    def test_a_value_the_pipe_run_derivation_refuses_falls_back_to_the_message_and_every_field(
        self, overrides: dict[str, Any], expected_values: str
    ) -> None:
        """A depth was repeated as given: a huge one raised ``OverflowError`` past the fallback and lost the line, or built a huge string."""
        record = record_with_fields(message="Pipe run starts", extra={**PIPE_RUN_FIELDS, **overrides}, layout=LogLayout.PIPE_RUN)

        text = rendered_text(record=record)

        assert text.plain == f"🧠: Pipe run starts pipe_type=PipeCompose pipe_code=compose_company output_concept=Company {expected_values}"

    def test_a_layout_that_cannot_be_filled_falls_back_to_the_message_and_every_field(self) -> None:
        text = rendered_text(record=record_with_fields(message="Pipe run starts", extra={"pipe_code": "compose_company"}, layout=LogLayout.PIPE_RUN))

        assert text.plain == "🧠: Pipe run starts pipe_code=compose_company"

    def test_a_layout_that_raises_anything_at_all_costs_only_itself(self, mocker: MockerFixture) -> None:
        """What a layout's derivation can raise is open-ended, and an error outside the ones the fallback named used to lose the line."""
        mocker.patch.object(PipeRunLayout, "derived_values", side_effect=OverflowError("cannot fit 'int' into an index-sized integer"))

        text = rendered_text(record=record_with_fields(message="Pipe run starts", extra={"pipe_code": "compose_company"}, layout=LogLayout.PIPE_RUN))

        assert text.plain == "🧠: Pipe run starts pipe_code=compose_company"

    def test_a_record_carrying_structured_content_keeps_its_message_and_every_field_follows_it(self, caplog: pytest.LogCaptureFixture) -> None:
        """The console never repeats ``data`` in the suffix because the message renders it, so a layout must not replace that message."""
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            fresh.info({"the_content_key": 1}, title="Pipe run starts", fields={**PIPE_RUN_FIELDS, "attempt": 2}, layout=LogLayout.PIPE_RUN)

        rendered = buffer.getvalue()
        assert "Pipe run starts:" in rendered
        assert '"the_content_key": 1' in rendered
        assert "} pipe_type=PipeCompose pipe_code=compose_company output_concept=Company pipe_depth=0 attempt=2" in rendered
        assert "→" not in rendered

    def test_a_content_json_refuses_keeps_its_message_rather_than_a_layout(self, caplog: pytest.LogCaptureFixture) -> None:
        """A circular content carries no ``data`` and lives only in the message's ``repr``, which a layout used to replace whole."""
        caplog.set_level(logging.INFO, logger=__name__)
        circular: dict[str, Any] = {"the_content_key": 1}
        circular["self"] = circular
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            fresh.info(circular, fields=PIPE_RUN_FIELDS, layout=LogLayout.PIPE_RUN)

        rendered = buffer.getvalue()
        assert "'the_content_key': 1" in rendered
        assert "pipe_code=compose_company" in rendered
        assert "→" not in rendered

    def test_a_content_a_record_factory_pushed_off_data_keeps_its_message_rather_than_a_layout(self, caplog: pytest.LogCaptureFixture) -> None:
        """A factory that owns ``data`` sends the content to ``field_data``, which a layout used to cut down to the suffix's short value."""
        caplog.set_level(logging.INFO, logger=__name__)
        long_value = "x" * (FIELD_VALUE_MAX_LENGTH + 20)
        previous_factory = logging.getLogRecordFactory()

        def stamping_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = previous_factory(*args, **kwargs)
            record.data = "data-from-factory"
            return record

        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            logging.setLogRecordFactory(stamping_factory)
            try:
                fresh.info({"the_content_key": long_value}, fields=PIPE_RUN_FIELDS, layout=LogLayout.PIPE_RUN)
            finally:
                logging.setLogRecordFactory(previous_factory)

        rendered = buffer.getvalue()
        assert f'"the_content_key": "{long_value}"' in rendered
        assert "→" not in rendered

    def test_a_record_whose_redaction_failed_shows_the_notice_rather_than_its_layout(
        self, caplog: pytest.LogCaptureFixture, mocker: MockerFixture
    ) -> None:
        """The quarantine turns the message into a notice and every field into ``[REDACTED]``.

        A layout left on the record drew those fields and hid the notice. The shipped layout refuses a redacted
        depth and would fall back by accident, so a layout that derives nothing stands in for it.
        """
        caplog.set_level(logging.INFO, logger=__name__)
        mocker.patch.dict(
            CONSOLE_LAYOUTS, {LogLayout.PIPE_RUN: ConsoleLayout(template="[red]{pipe_code}[/]", presented_fields=frozenset({"pipe_code"}))}
        )
        mocker.patch("pipelex.tools.log.log_redaction._redact_record", side_effect=RecursionError("too deep"))
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            fresh.info("Pipe run starts", fields={"pipe_code": "compose_company"}, layout=LogLayout.PIPE_RUN)

        rendered = buffer.getvalue()
        assert f"{QUARANTINE_PREFIX}RecursionError] pipe_code={REDACTED_TEXT}" in rendered
        assert "compose_company" not in rendered

    def test_a_layout_name_nobody_registered_renders_the_message(self) -> None:
        text = rendered_text(record=record_with_fields(message="Plain", extra={"files": 7}, layout="no_such_layout"))

        assert text.plain == "🧠: Plain files=7"

    def test_every_layout_a_call_can_name_is_registered(self) -> None:
        assert set(CONSOLE_LAYOUTS) == set(LogLayout)

    @pytest.mark.parametrize("template", ["{pipe.code}", "{pipe_code:>10}", "{pipe_code!r}", "{0}", "{codes[0]}"])
    def test_a_placeholder_other_than_a_bare_name_is_refused_at_registration(self, template: str) -> None:
        with pytest.raises(ValueError, match="bare name"):
            ConsoleLayout(template=template, presented_fields=frozenset())

    def test_the_json_sink_writes_the_plain_message_and_the_fields_and_never_the_layout(self, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        with installed_log(sink=JsonLogSink(stream=buffer)) as fresh:
            fresh.info("Pipe run starts", fields={**PIPE_RUN_FIELDS, "pipe_code": "[red]x[/red]"}, layout=LogLayout.PIPE_RUN)

        lines: list[dict[str, Any]] = [json.loads(line) for line in buffer.getvalue().splitlines() if line]
        (line,) = [line for line in lines if line[LOGGER_KEY] == __name__]
        assert line[MESSAGE_KEY] == "Pipe run starts"
        assert {key: line[key] for key in PIPE_RUN_FIELDS} == {**PIPE_RUN_FIELDS, "pipe_code": "[red]x[/red]"}
        assert LAYOUT_MARK not in line
        assert FIELD_NAMES_MARK not in line
        assert LogLayout.PIPE_RUN not in line.values()
