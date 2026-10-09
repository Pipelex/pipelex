from __future__ import annotations

import io
import json
import logging
from typing import Any

import pytest

from pipelex.tools.log.console_fields import FIELD_STYLES
from pipelex.tools.log.console_layouts import CONSOLE_LAYOUTS, ConsoleLayout, LogLayout
from pipelex.tools.log.json_log_sink import LOGGER_KEY, MESSAGE_KEY, JsonLogSink
from pipelex.tools.log.log_fields import FIELD_NAMES_MARK, LAYOUT_MARK
from tests.helpers.console_log_rendering import (
    PIPE_RUN_FIELDS,
    console_sink_on_buffer,
    installed_log,
    record_with_fields,
    rendered_text,
    styles_of,
)


class TestConsoleLayouts:
    @pytest.mark.parametrize(
        ("overrides", "expected"),
        [
            ({}, "PipeCompose: compose_company → Company"),
            ({"pipe_depth": 1}, "   ↳ PipeCompose: compose_company → Company"),
            ({"pipe_depth": 2, "is_dry_run": True}, "      ↳ Dry run: PipeCompose: compose_company → Company"),
        ],
        ids=["top level", "nested", "nested dry run"],
    )
    def test_the_pipe_run_layout_draws_the_tree_in_the_style_map_colours(self, overrides: dict[str, Any], expected: str) -> None:
        text = rendered_text(record=record_with_fields(message="Pipe run starts", extra={**PIPE_RUN_FIELDS, **overrides}, layout=LogLayout.PIPE_RUN))

        assert text.plain == f"🧠: {expected}"
        assert styles_of(text=text, fragment="compose_company") == [FIELD_STYLES["pipe_code"]]
        assert styles_of(text=text, fragment="Company") == [FIELD_STYLES["output_concept"]]

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
        ("extra", "expected"),
        [
            ({"pipe_code": "compose_company"}, "🧠: Pipe run starts pipe_code=compose_company"),
            (
                {**PIPE_RUN_FIELDS, "pipe_depth": "deep"},
                "🧠: Pipe run starts pipe_type=PipeCompose pipe_code=compose_company output_concept=Company pipe_depth=deep is_dry_run=false",
            ),
        ],
        ids=["a field missing", "a value the derivation refuses"],
    )
    def test_a_layout_that_cannot_be_filled_falls_back_to_the_message_and_every_field(self, extra: dict[str, Any], expected: str) -> None:
        text = rendered_text(record=record_with_fields(message="Pipe run starts", extra=extra, layout=LogLayout.PIPE_RUN))

        assert text.plain == expected

    def test_a_record_carrying_structured_content_keeps_its_message_and_every_field_follows_it(self, caplog: pytest.LogCaptureFixture) -> None:
        """The console never repeats ``data`` in the suffix because the message renders it, so a layout must not replace that message."""
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            fresh.info({"the_content_key": 1}, title="Pipe run starts", fields={**PIPE_RUN_FIELDS, "attempt": 2}, layout=LogLayout.PIPE_RUN)

        rendered = buffer.getvalue()
        assert "Pipe run starts:" in rendered
        assert '"the_content_key": 1' in rendered
        assert "} pipe_type=PipeCompose pipe_code=compose_company output_concept=Company pipe_depth=0 is_dry_run=false attempt=2" in rendered
        assert "→" not in rendered

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
