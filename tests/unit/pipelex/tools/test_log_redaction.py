"""Secrets are scrubbed and field values made injection-safe once, before any sink renders the record.

One test per shipped pattern family, each reading the scrubbed message and the scrubbed value of a
field, because a secret reaches a log agent through either. Field values are additionally stripped of
the control characters a caller could use to forge a line or a field separator; the message keeps its
newlines, which are the runtime's own rendering and not a caller's string.
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel
from typing_extensions import override

from pipelex.system.configuration.config_loader import ConfigLoader
from pipelex.tools.log.log import Log
from pipelex.tools.log.log_config import LogConfig, LogRedactionConfig
from pipelex.tools.log.log_fields import DATA_FIELD
from pipelex.tools.log.log_redaction import CYCLE_TEXT, REDACTED_TEXT, make_redaction_processor
from pipelex.tools.log.log_sink import LogSink
from pipelex.tools.misc.toml_utils import load_toml_from_path

if TYPE_CHECKING:
    from collections.abc import Iterator

    from pytest_mock import MockerFixture

FIELD_NAME = "payload"


def _package_log_config(*, is_redaction_enabled: bool = True) -> LogConfig:
    config_dict = load_toml_from_path(ConfigLoader().pipelex_root_dir / "pipelex.toml")
    redaction = {**config_dict["runtime"]["log"]["redaction"], "is_enabled": is_redaction_enabled}
    return LogConfig.model_validate({**config_dict["runtime"]["log"], "redaction": redaction})


def _record(*, text: str, value: Any = None) -> logging.LogRecord:
    """One record whose message is ``text`` and whose single field carries ``value``, or ``text`` again."""
    record = logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg=text, args=(), exc_info=None)
    record.payload = text if value is None else value
    return record


def _redact(*, text: str, extra_patterns: list[str] | None = None) -> tuple[str, Any]:
    """The message and the field value of one record, both carrying ``text``, after the processor ran."""
    record = _record(text=text)
    processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=extra_patterns or []))
    processor(record)
    return record.getMessage(), getattr(record, FIELD_NAME)


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    @override
    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


class _ListSink(LogSink):
    def __init__(self) -> None:
        super().__init__()
        self.list_handler = _ListHandler()

    @override
    def make_handler(self) -> logging.Handler:
        return self.list_handler

    def own_records(self) -> list[logging.LogRecord]:
        return [record for record in self.list_handler.records if record.name == __name__]


class TestLogRedaction:
    @pytest.fixture
    def fresh_log(self, caplog: pytest.LogCaptureFixture) -> Iterator[Log]:
        # pytest's ``log_level`` option restores the root logger's level at every phase boundary, undoing the
        # level ``configure`` sets from inside a fixture; the module's own logger is enabled explicitly and
        # ``caplog`` restores it at teardown.
        caplog.set_level(logging.INFO, logger=__name__)
        fresh = Log()
        try:
            yield fresh
        finally:
            fresh.reset()

    def test_a_bearer_token_in_an_authorization_header_is_scrubbed(self) -> None:
        message, value = _redact(text="calling with Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.body.signature now")

        assert message == f"calling with Authorization: Bearer {REDACTED_TEXT} now"
        assert value == f"calling with Authorization: Bearer {REDACTED_TEXT} now"

    def test_an_api_key_header_value_is_scrubbed(self) -> None:
        message, value = _redact(text="x-api-key: abcd1234efgh5678ijkl")

        assert message == f"x-api-key: {REDACTED_TEXT}"
        assert value == f"x-api-key: {REDACTED_TEXT}"

    def test_a_signature_header_value_is_scrubbed(self) -> None:
        message, value = _redact(text="x-completion-signature=0123456789abcdef0123")

        assert message == f"x-completion-signature={REDACTED_TEXT}"
        assert value == f"x-completion-signature={REDACTED_TEXT}"

    def test_an_oauth_code_query_parameter_is_scrubbed(self) -> None:
        message, value = _redact(text="redirected to /callback?code=4-0AfJohXm1n2o3p4q5&state=xyz")

        assert message == f"redirected to /callback?code={REDACTED_TEXT}&state=xyz"
        assert value == f"redirected to /callback?code={REDACTED_TEXT}&state=xyz"

    def test_a_cookie_header_value_is_scrubbed(self) -> None:
        message, value = _redact(text="Set-Cookie: session=3f9a2b7c4d1e")

        assert message == f"Set-Cookie: {REDACTED_TEXT}"
        assert value == f"Set-Cookie: {REDACTED_TEXT}"

    def test_every_crumb_of_a_multi_cookie_header_is_scrubbed_and_the_next_line_survives(self) -> None:
        message, value = _redact(text="Cookie: theme=light; session=private_session_12345\nUser ada logged in")

        assert message == f"Cookie: {REDACTED_TEXT}\nUser ada logged in"
        assert value == f"Cookie: {REDACTED_TEXT}\\nUser ada logged in"

    def test_a_serialised_cookie_entry_is_scrubbed_up_to_its_closing_quote(self) -> None:
        message, _ = _redact(text='{"cookie": "a=b; session=private_session_12345", "path": "/x"}')

        assert message == f'{{"cookie": "{REDACTED_TEXT}", "path": "/x"}}'

    def test_prose_that_merely_mentions_a_cookie_is_left_alone(self) -> None:
        message, _ = _redact(text="the cookie was set and the rest of this sentence survives")

        assert message == "the cookie was set and the rest of this sentence survives"

    def test_a_json_secret_value_holding_the_other_quote_character_is_scrubbed_whole(self) -> None:
        message, _ = _redact(text='{"password": "prefix\'private_suffix_12345", "next": "kept"}')

        assert message == f'{{"password": "{REDACTED_TEXT}", "next": "kept"}}'

    def test_a_json_secret_value_holding_an_escaped_quote_is_scrubbed_whole(self) -> None:
        message, _ = _redact(text='{"access_token": "ab\\"cd_private_12345", "next": "kept"}')

        assert message == f'{{"access_token": "{REDACTED_TEXT}", "next": "kept"}}'

    def test_a_json_code_entry_is_not_a_secret(self) -> None:
        message, value = _redact(text='{"error_type": "PipeDefinitionError", "code": "PIPE_NOT_FOUND"}')

        assert message == '{"error_type": "PipeDefinitionError", "code": "PIPE_NOT_FOUND"}'
        assert value == '{"error_type": "PipeDefinitionError", "code": "PIPE_NOT_FOUND"}'

    def test_a_json_secret_field_is_scrubbed_and_keeps_its_shape(self) -> None:
        message, value = _redact(text='{"user": "ada", "password": "hunter2hunter2", "access_token": "at-9f3c"}')

        assert message == f'{{"user": "ada", "password": "{REDACTED_TEXT}", "access_token": "{REDACTED_TEXT}"}}'
        assert value == f'{{"user": "ada", "password": "{REDACTED_TEXT}", "access_token": "{REDACTED_TEXT}"}}'

    def test_an_api_key_prefix_is_scrubbed_wherever_it_appears(self) -> None:
        text = "keys sk_live_0123456789abcdef plx_sk_0123456789abcdef pk_live_0123456789abcdef bl_0123456789abcdef seen"
        expected = f"keys {REDACTED_TEXT} {REDACTED_TEXT} {REDACTED_TEXT} {REDACTED_TEXT} seen"

        message, value = _redact(text=text)

        assert message == expected
        assert value == expected

    def test_a_control_character_in_a_field_value_is_neutralised_and_the_message_keeps_its_newlines(self) -> None:
        message, value = _redact(text="ok\nstatus=200\tevent=forged\x1b[31m")

        assert message == "ok\nstatus=200\tevent=forged\x1b[31m"
        assert value == "ok\\nstatus=200\\tevent=forged\\x1b[31m"

    def test_a_configured_extra_pattern_is_scrubbed_beside_the_shipped_families(self) -> None:
        message, value = _redact(text="tenant tnt-40718 on sk_live_0123456789abcdef", extra_patterns=[r"tnt-[0-9]+"])

        assert message == f"tenant {REDACTED_TEXT} on {REDACTED_TEXT}"
        assert value == f"tenant {REDACTED_TEXT} on {REDACTED_TEXT}"

    def test_an_extra_pattern_the_re_module_refuses_is_a_configuration_error_naming_it(self) -> None:
        with pytest.raises(ValueError, match=r"\(unclosed"):
            LogRedactionConfig(is_enabled=True, extra_patterns=["(unclosed"])

    def test_a_secret_nested_in_a_structured_value_is_scrubbed_and_a_non_string_is_untouched(self) -> None:
        record = logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="sending", args=(), exc_info=None)
        record.payload = {"sent": "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.body.sig", "notes": ["a\nb", "sk_live_0123456789abcdef"], "attempt": 3}
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert getattr(record, FIELD_NAME) == {
            "sent": f"Authorization: Bearer {REDACTED_TEXT}",
            "notes": ["a\\nb", REDACTED_TEXT],
            "attempt": 3,
        }

    def test_a_value_that_contains_itself_is_cut_at_the_cycle_rather_than_walked_forever_or_kept_raw(self) -> None:
        """The raw container kept in the cleaned result would hand its unscrubbed strings to the sink's ``repr`` fallback."""
        cyclic: dict[str, Any] = {"token": "sk_live_0123456789abcdef"}
        cyclic["me"] = cyclic
        record = _record(text="cyclic", value=cyclic)
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert getattr(record, FIELD_NAME) == {"token": REDACTED_TEXT, "me": CYCLE_TEXT}

    def test_a_mapping_entry_named_like_a_secret_loses_its_value_whatever_it_holds(self) -> None:
        """The families read a name and a value out of one string; a mapping splits them, so the key is what names the secret."""
        record = _record(
            text="sending",
            value={"Authorization": "Bearer short", "x-api-key": "k", "password": {"nested": "p"}, "code": "PIPE_NOT_FOUND", "user": "ada"},
        )
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert getattr(record, FIELD_NAME) == {
            "Authorization": REDACTED_TEXT,
            "x-api-key": REDACTED_TEXT,
            "password": REDACTED_TEXT,
            "code": "PIPE_NOT_FOUND",
            "user": "ada",
        }

    def test_a_model_is_dumped_and_an_object_is_rendered_before_the_walk_so_the_sink_meets_scrubbed_text(self) -> None:
        """The sink would dump the model and render the object after the processor ran; the processor does it first so neither escapes the scrub."""

        class Credentials(BaseModel):
            api_key: str
            note: str

        class Carrier:
            @override
            def __str__(self) -> str:
                return "carrying sk_live_0123456789abcdef"

        record = _record(text="sending", value={"model": Credentials(api_key="plx_sk_ABCDEFGHIJKLMNOPQRSTU", note="line\nforged"), "object": Carrier()})
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert getattr(record, FIELD_NAME) == {"model": {"api_key": REDACTED_TEXT, "note": "line\\nforged"}, "object": f"carrying {REDACTED_TEXT}"}

    def test_the_data_attribute_is_scrubbed_of_secrets_but_keeps_its_control_characters(self) -> None:
        """``data`` is the runtime's own rendering of a structured content, which the wire sinks escape themselves, so a logged prompt keeps its newlines."""
        record = _record(text="prompt", value="ignored")
        setattr(record, DATA_FIELD, {"prompt": "line one\nline two", "token": "sk_live_0123456789abcdef"})
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert getattr(record, DATA_FIELD) == {"prompt": "line one\nline two", "token": REDACTED_TEXT}

    def test_the_scrub_edits_the_record_every_handler_shares_rather_than_a_copy(self, fresh_log: Log) -> None:
        """In place, not on a copy: a handler ordered after the sink is behind the scrub instead of being handed what the sink was spared."""
        fresh_log.configure(log_config=_package_log_config())
        sink = _ListSink()
        fresh_log.install_sink(sink)
        record = _record(text="token sk_live_0123456789abcdef", value="line\nforged")

        sink.handler.handle(record)

        (delivered,) = sink.own_records()
        assert delivered is record
        assert record.getMessage() == f"token {REDACTED_TEXT}"
        assert getattr(record, FIELD_NAME) == "line\\nforged"

    def test_a_sink_installed_again_after_a_reset_carries_one_redaction_processor(self, fresh_log: Log) -> None:
        """``reset`` takes back the processor ``install_sink`` put on the sink, so a reused sink object does not scrub twice or under a stale configuration."""
        sink = _ListSink()
        fresh_log.configure(log_config=_package_log_config())
        fresh_log.install_sink(sink)
        processors_after_one_install = list(sink.processors)

        fresh_log.reset()
        assert sink.processors == []
        fresh_log.configure(log_config=_package_log_config())
        fresh_log.install_sink(sink)

        assert len(sink.processors) == len(processors_after_one_install)

    def test_no_processor_is_installed_when_the_configuration_turns_redaction_off(self, fresh_log: Log) -> None:
        fresh_log.configure(log_config=_package_log_config(is_redaction_enabled=False))
        sink = _ListSink()
        fresh_log.install_sink(sink)
        record = _record(text="token sk_live_0123456789abcdef", value="line\nkept")

        sink.handler.handle(record)

        assert sink.processors == []
        assert record.getMessage() == "token sk_live_0123456789abcdef"
        assert getattr(record, FIELD_NAME) == "line\nkept"

    def test_an_exceptions_text_is_rendered_and_scrubbed_before_any_sink_reads_it(self) -> None:
        """The stdlib renders the traceback lazily into ``exc_text``; the processor renders it first, scrubbed, and every formatter reads that."""
        try:
            msg = "auth failed for sk_live_0123456789abcdef with Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.body.sig"
            raise RuntimeError(msg)
        except RuntimeError:
            record = logging.LogRecord(name=__name__, level=logging.ERROR, pathname="", lineno=0, msg="failed", args=(), exc_info=sys.exc_info())
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert record.exc_info is not None
        assert record.exc_text is not None
        assert "Traceback (most recent call last)" in record.exc_text
        assert record.exc_text.endswith(f"RuntimeError: auth failed for {REDACTED_TEXT} with Authorization: Bearer {REDACTED_TEXT}")
        assert logging.Formatter().format(record).endswith(record.exc_text)

    def test_an_already_rendered_exception_text_is_scrubbed_in_place(self) -> None:
        record = _record(text="failed")
        record.exc_text = "RuntimeError: key sk_live_0123456789abcdef refused"
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert record.exc_text == f"RuntimeError: key {REDACTED_TEXT} refused"

    def test_a_record_whose_cleaning_fails_is_quarantined_rather_than_handed_on_raw(self, mocker: MockerFixture) -> None:
        """Redaction fails closed: whatever the walk raised, the sink meets a record with nothing of the call left on it."""
        mocker.patch("pipelex.tools.log.log_redaction._redact_record", side_effect=RecursionError("too deep"))
        try:
            msg = "key sk_live_0123456789abcdef refused"
            raise RuntimeError(msg)
        except RuntimeError:
            record = logging.LogRecord(
                name=__name__, level=logging.ERROR, pathname="", lineno=0, msg="token %s", args=("sk_live_0123456789abcdef",), exc_info=sys.exc_info()
            )
        record.payload = {"nested": "sk_live_0123456789abcdef"}
        setattr(record, DATA_FIELD, ["sk_live_0123456789abcdef"])
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        with pytest.raises(RecursionError):
            processor(record)

        assert record.getMessage() == "[REDACTION FAILED: RecursionError]"
        assert record.args == ()
        assert getattr(record, FIELD_NAME) == REDACTED_TEXT
        assert getattr(record, DATA_FIELD) == REDACTED_TEXT
        assert record.exc_info is None
        assert record.exc_text is None
        assert "sk_live" not in logging.Formatter().format(record)

    def test_a_record_whose_message_cannot_be_rendered_keeps_its_scrubbed_fields_and_raises_nothing(self) -> None:
        record = logging.LogRecord(name=__name__, level=logging.INFO, pathname="", lineno=0, msg="%d items", args=("not a number",), exc_info=None)
        record.payload = "sk_live_0123456789abcdef"
        processor = make_redaction_processor(config=LogRedactionConfig(is_enabled=True, extra_patterns=[]))

        processor(record)

        assert record.msg == "%d items"
        assert getattr(record, FIELD_NAME) == REDACTED_TEXT
