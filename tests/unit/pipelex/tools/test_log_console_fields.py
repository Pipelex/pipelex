from __future__ import annotations

import io
import json
import logging
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.tools.log.console_fields import (
    ERROR_MESSAGE_MAX_LENGTH,
    FIELD_KEY_STYLE,
    FIELD_STYLES,
    FIELD_VALUE_MAX_LENGTH,
    FINDING_MESSAGE_FIELD,
    TRUNCATION_MARK,
    UNMAPPED_FIELD_STYLE,
    field_is_cut_at_start,
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

    @pytest.mark.parametrize(
        ("name", "is_cut_at_start"),
        [
            ("file.path", True),
            ("url.path", True),
            ("root_path", True),
            ("backup_path", True),
            ("override_paths", True),
            ("mthds_paths", True),
            ("library_dirs", True),
            ("target_dir", True),
            ("template_file", True),
            ("include_files", True),
            ("file.name", True),
            ("storage_key", True),
            (f"{COLLIDING_FIELD_PREFIX}override_paths", True),
            ("file_count", False),
            ("structure_classes", False),
            ("url.full", False),
            ("module_name", False),
            ("error.message", False),
            ("excerpt", False),
        ],
    )
    def test_a_field_is_taken_for_a_path_by_its_name(self, name: str, is_cut_at_start: bool) -> None:
        """Only the names listed one by one were cut at their start, so ``override_paths`` and every other path field lost the file's name."""
        assert field_is_cut_at_start(name=name) is is_cut_at_start

    @pytest.mark.parametrize("path_field", ["file.path", "file.name", "backup_path", "template_file", "root_path", "storage_key"])
    def test_a_long_path_is_cut_at_its_start_so_the_file_name_stays(self, path_field: str) -> None:
        """Cut at its end, a long path kept the directory every line of a run shares and lost the file's name."""
        long_path = "/Users/someone/projects/acme/" + "nested-directory/" * 8 + "invoice_template_v2.docx"
        text = rendered_text(record=record_with_fields(message="Read", extra={path_field: long_path, "excerpt": "x" * 500}))

        kept_tail = long_path[len(long_path) - FIELD_VALUE_MAX_LENGTH + len(TRUNCATION_MARK) :]
        assert f"{path_field}={TRUNCATION_MARK}{kept_tail} " in text.plain
        assert kept_tail.endswith("/invoice_template_v2.docx")
        assert "/Users/someone" not in text.plain
        assert text.plain.endswith(f"excerpt={'x' * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK))}{TRUNCATION_MARK}")

    @pytest.mark.parametrize(
        ("path_field", "paths", "file_name"),
        [
            (
                "override_paths",
                ["/private/tmp/scratch/-Users-someone-projects-acme/8c7e235e-b5d9-4299-9cca-4821d85192a0/.pipelex/backends_override.toml"],
                "backends_override.toml",
            ),
            (
                "library_dirs",
                ["/Users/someone/projects/acme/methods", "/Users/someone/projects/acme/shared/libraries", "/Users/someone/My methods/a b=c/invoices"],
                "invoices",
            ),
        ],
        ids=["one long override file", "several library directories"],
    )
    def test_a_long_list_of_paths_is_cut_at_its_start_so_the_last_file_name_stays(self, path_field: str, paths: list[str], file_name: str) -> None:
        """Cut at its end, the boot's backends line kept a temporary directory and lost the override file's name.

        The rendering is cut before it is quoted and escaped, so the cut list is one quoted value, and neither a space
        nor an equals sign in its last path reads as a pair of its own.
        """
        text = rendered_text(record=record_with_fields(message="Read", extra={path_field: paths, "attempt": 2}))

        rendering = json.dumps(paths, ensure_ascii=False, separators=(",", ":"))
        kept_tail = rendering[len(rendering) - FIELD_VALUE_MAX_LENGTH + len(TRUNCATION_MARK) :]
        quoted = '"' + f"{TRUNCATION_MARK}{kept_tail}".replace("\\", "\\\\").replace('"', '\\"') + '"'
        assert len(rendering) > FIELD_VALUE_MAX_LENGTH
        assert kept_tail.endswith(f'/{file_name}"]')
        assert text.plain.endswith(f"{path_field}={quoted} attempt=2")
        # The value is one quoted span: every quote inside it is escaped, so nothing after a space reads as a pair.
        assert '"' not in quoted[1:-1].replace('\\"', "")

    def test_a_long_value_of_a_field_not_named_as_a_path_is_still_cut_at_its_end(self) -> None:
        """Only a path field is cut at its start: a text naming files, by a name no path ending reaches, keeps its start."""
        structure_classes = "invoices/structures.py: Invoice, Line; " * 4
        text = rendered_text(record=record_with_fields(message="Fetched", extra={"structure_classes": structure_classes, "attempt": 2}))

        kept_head = structure_classes[: FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK)]
        assert text.plain.endswith(f'structure_classes="{kept_head}{TRUNCATION_MARK}" attempt=2')

    @pytest.mark.parametrize(
        ("topic", "file_name"),
        [
            ("a space", "file fake=value.txt"),
            ("an equals sign", "file=fake.txt"),
        ],
    )
    def test_a_long_quoted_path_is_cut_before_it_is_quoted_so_its_quotes_stay_balanced(self, topic: str, file_name: str) -> None:
        """Cut after quoting, the path lost its opening quote, and its tail read as a pair of its own: ``file.path=…/file fake=value.txt"``."""
        long_path = "/Users/someone/projects/acme/" + "nested-directory/" * 8 + file_name
        text = rendered_text(record=record_with_fields(message="Read", extra={"file.path": long_path, "attempt": 2}))

        kept_tail = long_path[len(long_path) - FIELD_VALUE_MAX_LENGTH + len(TRUNCATION_MARK) :]
        assert text.plain.endswith(f'file.path="{TRUNCATION_MARK}{kept_tail}" attempt=2'), topic
        assert kept_tail.endswith(f"/{file_name}"), topic

    def test_a_long_quoted_value_is_cut_before_it_is_quoted_so_its_closing_quote_stays(self) -> None:
        """Cut after quoting, a long spaced value lost its closing quote, and every pair after it read as part of it."""
        excerpt = "two words " * 20
        text = rendered_text(record=record_with_fields(message="Read", extra={"excerpt": excerpt, "attempt": 2}))

        kept_head = excerpt[: FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK)]
        assert text.plain.endswith(f'excerpt="{kept_head}{TRUNCATION_MARK}" attempt=2')

    def test_a_cut_never_splits_an_escape(self) -> None:
        """A quote escaped at the cut kept its backslash and lost the quote, and the backslash then escaped the closing one."""
        excerpt = "x" * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK) - 1) + '"' + "y" * 40
        text = rendered_text(record=record_with_fields(message="Read", extra={"excerpt": excerpt, "attempt": 2}))

        assert text.plain.endswith(f'excerpt="{"x" * (FIELD_VALUE_MAX_LENGTH - len(TRUNCATION_MARK) - 1)}\\"{TRUNCATION_MARK}" attempt=2')

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
