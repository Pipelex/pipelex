from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.tools.log.console_fields import (
    ERROR_MESSAGE_MAX_LENGTH,
    FIELD_KEY_STYLE,
    FIELD_STYLES,
    FIELD_VALUE_MAX_LENGTH,
    FINDING_MESSAGE_FIELD,
    LEFT_CUT_FIELDS,
    TRUNCATION_MARK,
    UNMAPPED_FIELD_STYLE,
)
from pipelex.tools.log.error_fields import error_fields
from pipelex.tools.log.log_fields import (
    COLLIDING_FIELD_PREFIX,
    FIELD_NAMES_MARK,
    RICH_HIGHLIGHTER_ATTRIBUTE,
    RICH_MARKUP_ATTRIBUTE,
    attach_log_record_extra,
)
from tests.helpers.console_log_rendering import (
    console_sink_on_buffer,
    installed_log,
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

        fresh.info("Renamed", fields={"name": "alpha", RICH_MARKUP_ATTRIBUTE: True})

        assert "Renamed field_name=alpha field_markup=true" in buffer.getvalue()

    def test_a_field_named_like_rich_s_highlighter_override_keeps_the_line(self, console_log: tuple[Log, io.StringIO]) -> None:
        """Rich calls whatever the record carries as ``highlighter``, so a string field of that name raised inside the handler and lost the line."""
        fresh, buffer = console_log

        fresh.info("Highlighted", fields={RICH_HIGHLIGHTER_ATTRIBUTE: "pygments"})

        assert f"Highlighted {COLLIDING_FIELD_PREFIX}{RICH_HIGHLIGHTER_ATTRIBUTE}=pygments" in buffer.getvalue()

    @pytest.mark.parametrize(
        ("fields", "expected"),
        [
            ({"x=1": 2}, 'Paired "x=1"=2'),
            ({"a": "b=c"}, 'Paired a="b=c"'),
            ({'say"': 'it"s'}, 'Paired "say\\""="it\\"s"'),
            ({"path": "C:\\dir"}, 'Paired path="C:\\\\dir"'),
        ],
        ids=["an equals sign in a key", "an equals sign in a value", "a quote", "a backslash"],
    )
    def test_a_key_or_value_that_could_forge_a_pair_is_quoted(
        self, console_log: tuple[Log, io.StringIO], fields: dict[str, Any], expected: str
    ) -> None:
        """Printed bare, ``{"x=1": 2}`` read as ``x=1=2`` and ``{"a": "b=c"}`` as ``a=b=c``.

        An unescaped backslash could also end a quoted value early.
        """
        fresh, buffer = console_log

        fresh.info("Paired", fields=fields)

        assert expected in buffer.getvalue()

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

    def test_neither_the_message_nor_a_value_is_read_as_markup(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        fresh.info("[bold]Received[/bold]", fields={"detail": "[red]x[/red]"})

        assert "[bold]Received[/bold] detail=[red]x[/red]" in buffer.getvalue()

    def test_a_long_value_is_cut_short(self, console_log: tuple[Log, io.StringIO]) -> None:
        fresh, buffer = console_log

        fresh.info("Long", fields={"excerpt": "x" * 500})

        rendered = buffer.getvalue()
        assert f"excerpt={'x' * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}" in rendered
        assert "x" * FIELD_VALUE_MAX_LENGTH not in rendered

    def test_an_error_message_gets_a_generous_cut_while_other_fields_stay_cut_short(self) -> None:
        """The cause chain of an unresolved package outgrows the common cut, and a fragment ending in an ellipsis loses the diagnosis."""
        causes = "PackageFetchError: could not clone 'github.com/acme/methods' <- GitError: " + "fatal: repository not found; " * 6
        text = rendered_text(
            record=record_with_fields(
                message="A method package could not be resolved",
                extra={"package_address": "github.com/acme/methods", **error_fields(exc=RuntimeError("boom"), text=causes), "excerpt": "x" * 500},
            ),
        )

        quoted_causes = '"' + causes.replace('"', '\\"') + '"'
        assert f"error.message={quoted_causes}" in text.plain
        assert TRUNCATION_MARK + " excerpt=" not in text.plain
        assert f"excerpt={'x' * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}" in text.plain

    def test_an_error_message_past_its_own_cut_is_cut_short(self) -> None:
        """A dependency's raw output, a validation error's every line, never floods the console."""
        flood = "y" * (2 * ERROR_MESSAGE_MAX_LENGTH)
        text = rendered_text(record=record_with_fields(message="A method package could not be resolved", extra=error_fields(exc=RuntimeError(flood))))

        assert text.plain.endswith(f"error.message={'y' * (ERROR_MESSAGE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}")
        assert "y" * ERROR_MESSAGE_MAX_LENGTH not in text.plain

    @pytest.mark.parametrize("path_field", sorted(LEFT_CUT_FIELDS))
    def test_a_long_path_is_cut_at_its_start_so_the_file_name_stays(self, path_field: str) -> None:
        """Cut at its end, a long path kept the directory every line of a run shares and lost the file's name."""
        long_path = "/Users/someone/projects/acme/" + "nested-directory/" * 8 + "invoice_template_v2.docx"
        text = rendered_text(record=record_with_fields(message="Read", extra={path_field: long_path, "excerpt": "x" * 500}))

        kept_tail = long_path[len(long_path) - FIELD_VALUE_MAX_LENGTH + len(TRUNCATION_MARK) :]
        assert f"{path_field}={TRUNCATION_MARK}{kept_tail} " in text.plain
        assert kept_tail.endswith("/invoice_template_v2.docx")
        assert "/Users/someone" not in text.plain
        assert text.plain.endswith(f"excerpt={'x' * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}")

    def test_a_short_path_is_written_whole(self) -> None:
        text = rendered_text(record=record_with_fields(message="Read", extra={"file.path": "/repo/.pipelex/pipelex.toml"}))

        assert text.plain.endswith("file.path=/repo/.pipelex/pipelex.toml")

    def test_a_template_finding_gets_the_error_message_cut(self) -> None:
        """The finding is the actionable part of a PipeDocGen template warning, and the common cut lost it to a fragment."""
        finding = "The placeholder 'invoice.lines' is read as a list but the step's input 'invoice' declares it a single " + "Line; " * 20
        flood = "z" * (2 * ERROR_MESSAGE_MAX_LENGTH)
        whole = rendered_text(record=record_with_fields(message="Checked", extra={FINDING_MESSAGE_FIELD: finding}))
        flooded = rendered_text(record=record_with_fields(message="Checked", extra={FINDING_MESSAGE_FIELD: flood}))

        assert len(finding) > FIELD_VALUE_MAX_LENGTH
        assert whole.plain.endswith(f'{FINDING_MESSAGE_FIELD}="' + finding.replace('"', '\\"') + '"')
        assert flooded.plain.endswith(f"{FINDING_MESSAGE_FIELD}={'z' * (ERROR_MESSAGE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}")

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

    def test_a_field_a_record_factory_pushed_under_the_prefix_keeps_its_colour(self) -> None:
        """The style used to be looked up by the name the field landed on, so ``field_pipe_code`` printed dimmed."""
        record = logging.LogRecord(
            name="pipelex.tools.demo", level=logging.INFO, pathname="/repo/pipelex/module.py", lineno=42, msg="Running", args=(), exc_info=None
        )
        record.pipe_code = "from-factory"
        attach_log_record_extra(record=record, extra={"pipe_code": "compose_company"})

        text = rendered_text(record=record)

        assert text.plain == f"🧠: Running {COLLIDING_FIELD_PREFIX}pipe_code=compose_company"
        assert styles_of(text=text, fragment="compose_company") == [FIELD_STYLES["pipe_code"]]

    def test_what_a_record_factory_or_the_runtime_stamped_is_not_shown(self) -> None:
        record = record_with_fields(message="Stamped", extra={"files": 7})
        record.otelSpanID = "0"
        record.__dict__[RICH_MARKUP_ATTRIBUTE] = False

        text = rendered_text(record=record)

        assert text.plain == "🧠: Stamped files=7"
        assert FIELD_NAMES_MARK not in text.plain

    def test_a_record_the_fields_channel_never_saw_renders_its_message_alone(self) -> None:
        record = logging.LogRecord(name="httpx", level=logging.INFO, pathname="/x.py", lineno=1, msg="HTTP Request", args=(), exc_info=None)
        record.custom = "a library's own extra"

        text = rendered_text(record=record)

        assert text.plain.endswith("HTTP Request")
        assert "custom" not in text.plain
