from __future__ import annotations

import textwrap

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import LogCallRule, OffendingCall, find_offending_calls_in_source

SAMPLE_PATH = "pipelex/core/sample_module.py"
HEADER = "from pipelex import log\nfrom pipelex.tools.log import error_fields\n"

EVERY_METHOD = ["verbose", "debug", "info", "warning", "error", "critical"]


def _offending(body: str) -> list[OffendingCall]:
    return find_offending_calls_in_source(source=HEADER + textwrap.dedent(body), relative_path=SAMPLE_PATH)


def _rules(body: str) -> list[list[LogCallRule]]:
    return [[breach.rule for breach in call.breaches] for call in _offending(body)]


def _details(body: str, *, rule: LogCallRule) -> list[str]:
    return [breach.detail for call in _offending(body) for breach in call.breaches if breach.rule == rule]


class TestLogCallGuardSplicedException:
    @pytest.mark.parametrize("method", EVERY_METHOD)
    @pytest.mark.parametrize(
        ("topic", "message", "expected_source"),
        [
            ("an f-string placeholder", 'f"A cleanup failed: {exc}"', "exc"),
            ("a converted placeholder", 'f"A cleanup failed: {exc!r}"', "exc"),
            ("an expression of the exception", 'f"A cleanup failed: {type(exc).__name__}"', "type(exc).__name__"),
            ("a percent format", '"A cleanup failed: %s" % exc', "exc"),
            ("a percent format of a tuple", '"A cleanup of %s failed: %s" % (path, exc)', "(path, exc)"),
            ("a .format() argument", '"A cleanup failed: {}".format(exc)', "exc"),
            ("a .format() keyword", '"A cleanup failed: {error}".format(error=exc)', "exc"),
            ("the exception as the message", "exc", "exc"),
            ("the exception's text as the message", "str(exc)", "str(exc)"),
            ("the exception's text concatenated", '"A cleanup failed: " + str(exc)', "str(exc)"),
        ],
    )
    def test_a_handled_exception_spliced_into_the_text_is_refused_at_every_level(
        self, method: str, topic: str, message: str, expected_source: str
    ) -> None:
        body = f"def clean(path):\n    try:\n        path.unlink()\n    except OSError as exc:\n        log.{method}({message})\n"
        assert _details(body, rule=LogCallRule.SPLICED_EXCEPTION) == [f"the message splices the exception `{expected_source}`"], topic

    def test_an_exception_method_s_result_is_refused_wherever_it_is_called(self) -> None:
        """A finished task's or a retry outcome's `.exception()` is the exception, though no handler binds it."""
        body = 'def clean(task):\n    task.add_done_callback(lambda t: log.debug(f"A cleanup failed: {t.exception()}"))\n'
        assert _details(body, rule=LogCallRule.SPLICED_EXCEPTION) == ["the message splices the exception `t.exception()`"]

    @pytest.mark.parametrize(
        ("topic", "body", "expected_signature"),
        [
            (
                "a placeholder naming the handler's target",
                '    except OSError as exc:\n        log.debug(f"A cleanup failed: {exc}")\n',
                'debug: f"A cleanup failed: {exc}" [spliced-exception] where exc = <except target>',
            ),
            (
                "a message bound to an f-string splicing it",
                '    except OSError as exc:\n        msg = f"A cleanup failed: {exc}"\n        log.debug(msg)\n',
                'debug: msg [spliced-exception] where exc = <except target>; msg = f"A cleanup failed: {exc}"',
            ),
            (
                "a placeholder naming the exception's text",
                '    except OSError as exc:\n        detail = str(exc)\n        log.debug(f"A cleanup failed: {detail}")\n',
                'debug: f"A cleanup failed: {detail}" [spliced-exception] where detail = str(exc); exc = <except target>',
            ),
            (
                "a name captured from the handler by a callback",
                '    except OSError as exc:\n        path.on_close(lambda: log.debug(f"A cleanup failed: {exc}"))\n',
                'debug: f"A cleanup failed: {exc}" [spliced-exception] where exc = <except target>',
            ),
        ],
    )
    def test_the_exception_is_followed_through_the_bindings_that_reach_it(self, topic: str, body: str, expected_signature: str) -> None:
        """The signature carries the bindings the exception is reached through, the handler's target last in the route."""
        source = f"def clean(path):\n    try:\n        path.unlink()\n{body}"
        assert [call.signature for call in _offending(source)] == [expected_signature], topic

    @pytest.mark.parametrize(
        ("topic", "body"),
        [
            ("a parameter named like an exception", 'def clean(exc):\n    log.debug(f"A cleanup failed: {exc}")\n'),
            (
                "the exception in fields",
                (
                    "def clean(path):\n    try:\n        path.unlink()\n    except OSError as exc:\n"
                    '        log.warning("A cleanup failed", fields={**error_fields(exc=exc)})\n'
                ),
            ),
            (
                "the exception on the record at ERROR",
                (
                    "def clean(path):\n    try:\n        path.unlink()\n    except OSError:\n"
                    '        log.error("A cleanup failed", include_exception=True)\n'
                ),
            ),
            (
                "a name the handler bound, rebound before the read",
                (
                    "def clean(path):\n    try:\n        path.unlink()\n    except OSError as exc:\n        pass\n"
                    '    exc = path.name\n    log.debug(f"A cleanup ran on {exc}")\n'
                ),
            ),
            (
                "a value of the handler that is not the exception",
                (
                    "def clean(path):\n    try:\n        path.unlink()\n    except OSError:\n        name = path.name\n"
                    '        log.debug(f"A cleanup of {name} failed")\n'
                ),
            ),
        ],
    )
    def test_a_message_that_reaches_no_handled_exception_passes(self, topic: str, body: str) -> None:
        assert _offending(body) == [], topic

    def test_an_interpolated_exception_at_info_and_above_breaks_both_rules(self) -> None:
        body = 'def clean(path):\n    try:\n        path.unlink()\n    except OSError as exc:\n        log.warning(f"A cleanup failed: {exc}")\n'
        assert _rules(body) == [[LogCallRule.F_STRING, LogCallRule.SPLICED_EXCEPTION]]
