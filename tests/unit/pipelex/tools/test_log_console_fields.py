from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING

import pytest

from pipelex.tools.log.console_fields import FIELD_KEY_STYLE, FIELD_STYLES, FIELD_VALUE_MAX_LENGTH, TRUNCATION_MARK, UNMAPPED_FIELD_STYLE
from pipelex.tools.log.log_fields import FIELD_NAMES_MARK, VERBATIM_MARK
from tests.helpers.console_log_rendering import (
    console_sink_on_buffer,
    installed_log,
    package_log_config,
    record_with_fields,
    rendered_text,
    styles_of,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pipelex.tools.log.log import Log


class TestConsoleFields:
    @pytest.fixture
    def console_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[tuple[Log, io.StringIO]]:
        """A fresh ``Log`` with the console sink on a buffer, the module's own logger enabled for the test."""
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, so the
        # module's own logger is enabled explicitly, and ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        buffer = io.StringIO()
        with installed_log(sink=console_sink_on_buffer(buffer=buffer)) as fresh:
            yield fresh, buffer

    def test_the_fields_follow_the_message_as_key_value(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        fresh.info("Scanned the inputs", fields={"files": 7})

        assert "Scanned the inputs files=7" in buffer.getvalue()

    def test_the_run_identifiers_and_the_structured_content_are_never_repeated(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        with fresh.context(request_id="req-1", pipeline_run_id="plr-1", pipe_run_id="pr-1"):
            fresh.info("Inside a run", fields={"files": 7})
            fresh.info({"key": "value"}, title="Config", fields={"attempt": 2})

        rendered = buffer.getvalue()
        assert "Inside a run files=7" in rendered
        assert "} attempt=2" in rendered
        for hidden in ("request_id", "pipeline_run_id", "pipe_run_id", "req-1", "plr-1", "pr-1", "data="):
            assert hidden not in rendered

    def test_a_field_named_like_a_record_attribute_or_a_mark_shows_under_the_name_it_landed_on(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        fresh.info("Renamed", fields={"name": "alpha", VERBATIM_MARK: True})

        assert "Renamed field_name=alpha field_markup=true" in buffer.getvalue()

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("hello\nFORGED", 'Keyed "hello\\nFORGED"=1'),
            ("two words", 'Keyed "two words"=1'),
            ("\x1b[2J", 'Keyed "\\x1b[2J"=1'),
        ],
        ids=["a line break", "a space", "an escape sequence"],
    )
    def test_a_key_is_written_like_a_value_so_it_forges_neither_a_line_nor_a_pair(
        self, console_log: tuple[Log, io.StringIO], name: str, expected: str
    ) -> None:
        """A field's name is the caller's text too: unescaped, a line break printed a forged ``FORGED=1`` line of its own."""
        fresh, buffer = console_log

        fresh.info("Keyed", fields={name: 1})

        rendered = buffer.getvalue()
        assert expected in rendered
        assert "\x1b" not in rendered
        assert not any(line.lstrip().startswith("FORGED") for line in rendered.splitlines())

    def test_a_value_carrying_markup_prints_as_written_while_the_message_still_reads_markup(self, console_log: tuple[Log, io.StringIO]) -> None:
        assert package_log_config().rich_log.is_markup_enabled, "the suffix must hold whatever the setting it runs beside"
        fresh, buffer = console_log

        fresh.info("[bold]Received[/bold]", fields={"detail": "[red]x[/red]"})

        rendered = buffer.getvalue()
        assert "Received detail=[red]x[/red]" in rendered
        assert "[bold]" not in rendered

    def test_a_long_value_is_cut_short(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        fresh.info("Long", fields={"excerpt": "x" * 500})

        rendered = buffer.getvalue()
        assert f"excerpt={'x' * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}" in rendered
        assert "x" * FIELD_VALUE_MAX_LENGTH not in rendered

    def test_a_field_is_styled_by_its_name_and_a_field_outside_the_map_is_dimmed(self) -> None:
        text = rendered_text(
            record=record_with_fields(
                message="Running",
                extra={"pipe_code": "compose_company", "output_concept": "Company", "pipe_type": "PipeLLM", "attempt": 2},
            ),
        )

        assert text.plain == "🧠: Running pipe_code=compose_company output_concept=Company pipe_type=PipeLLM attempt=2"
        assert styles_of(text=text, fragment="compose_company") == [FIELD_STYLES["pipe_code"]] == ["red"]
        assert styles_of(text=text, fragment="Company") == [FIELD_STYLES["output_concept"]] == ["bold green"]
        assert styles_of(text=text, fragment="PipeLLM") == [FIELD_STYLES["pipe_type"]] == ["white"]
        assert styles_of(text=text, fragment="2") == [UNMAPPED_FIELD_STYLE]
        assert styles_of(text=text, fragment="pipe_code=") == [FIELD_KEY_STYLE]

    def test_what_a_record_factory_or_the_runtime_stamped_is_not_shown(self) -> None:
        record = record_with_fields(message="Stamped", extra={"files": 7})
        record.otelSpanID = "0"
        record.__dict__[VERBATIM_MARK] = False

        text = rendered_text(record=record)

        assert text.plain == "🧠: Stamped files=7"
        assert FIELD_NAMES_MARK not in text.plain

    def test_a_record_the_fields_channel_never_saw_renders_its_message_alone(self) -> None:
        record = logging.LogRecord(name="httpx", level=logging.INFO, pathname="/x.py", lineno=1, msg="HTTP Request", args=(), exc_info=None)
        record.custom = "a library's own extra"

        text = rendered_text(record=record)

        assert text.plain.endswith("HTTP Request")
        assert "custom" not in text.plain
