from __future__ import annotations

import textwrap

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import MAX_MESSAGE_LENGTH, LogCallRule, OffendingCall, find_offending_calls_in_source

SAMPLE_PATH = "pipelex/core/sample_module.py"
HEADER = "from pipelex import log\nfrom pipelex.tools.log import error_fields\n"

EVERY_METHOD = ["verbose", "debug", "info", "warning", "error", "critical"]
INFO_AND_ABOVE = ["info", "warning", "error", "critical"]
BELOW_INFO = ["verbose", "debug"]


def _offending(body: str) -> list[OffendingCall]:
    return find_offending_calls_in_source(source=HEADER + textwrap.dedent(body), relative_path=SAMPLE_PATH)


def _rules(body: str) -> list[list[LogCallRule]]:
    return [[breach.rule for breach in call.breaches] for call in _offending(body)]


def _details(body: str, *, rule: LogCallRule) -> list[str]:
    return [breach.detail for call in _offending(body) for breach in call.breaches if breach.rule == rule]


class TestLogCallGuardWording:
    @pytest.mark.parametrize("method", EVERY_METHOD)
    @pytest.mark.parametrize(
        ("topic", "message", "expected_detail"),
        [
            ("a lowercase first word", '"loaded the library"', "the message starts with the lowercase `loaded`"),
            ("a lowercase word after leading whitespace", '"  loaded the library"', "the message starts with the lowercase `loaded`"),
            ("a lowercase file name", '"pipelex.toml was read"', "the message starts with the lowercase `pipelex.toml`"),
        ],
    )
    def test_a_lowercase_start_is_refused_at_every_level(self, method: str, topic: str, message: str, expected_detail: str) -> None:
        assert _details(f"def load():\n    log.{method}({message})\n", rule=LogCallRule.LOWERCASE_START) == [expected_detail], topic

    @pytest.mark.parametrize("method", EVERY_METHOD)
    @pytest.mark.parametrize(
        ("topic", "message", "expected_detail"),
        [
            ("a period", '"The library was loaded."', "the message ends with `.`"),
            ("an ellipsis of periods", '"Loading the library..."', "the message ends with `...`"),
            ("an ellipsis character", '"Loading the library…"', "the message ends with `…`"),
            ("a period before trailing whitespace", '"The library was loaded. "', "the message ends with `.`"),
        ],
    )
    def test_a_trailing_period_or_ellipsis_is_refused_at_every_level(self, method: str, topic: str, message: str, expected_detail: str) -> None:
        assert _details(f"def load():\n    log.{method}({message})\n", rule=LogCallRule.TRAILING_PERIOD) == [expected_detail], topic

    @pytest.mark.parametrize("method", EVERY_METHOD)
    def test_a_backtick_is_refused_at_every_level(self, method: str) -> None:
        body = f'def load():\n    log.{method}("The library was loaded with `strict` on")\n'
        assert _details(body, rule=LogCallRule.BACKTICK) == ["the message holds a backtick"]

    @pytest.mark.parametrize("method", EVERY_METHOD)
    @pytest.mark.parametrize(
        ("topic", "message"),
        [
            ("a capital start and no period", '"The library was loaded"'),
            ("a start that is no letter", '"3 pipes were loaded"'),
            ("a quoted start", "\"'strict' mode was turned on\""),
            ("a question mark", '"Was the library loaded?"'),
            ("a period inside the message", '"Version 1.2 of the library was loaded"'),
        ],
    )
    def test_a_message_worded_by_the_conventions_passes_at_every_level(self, method: str, topic: str, message: str) -> None:
        assert _offending(f"def load():\n    log.{method}({message})\n") == [], topic

    @pytest.mark.parametrize("method", BELOW_INFO)
    @pytest.mark.parametrize(
        ("topic", "message"),
        [
            ("a start an f-string splices", 'f"{alias} was loaded"'),
            ("an end an f-string splices", 'f"Loaded the library at {alias}"'),
            ("a start a value concatenates", 'alias + " was loaded"'),
        ],
    )
    def test_a_start_or_an_end_the_guard_cannot_read_passes(self, method: str, topic: str, message: str) -> None:
        """A value spliced at the start or the end could be anything, so nothing tells the rule is broken."""
        assert _offending(f"def load(alias):\n    log.{method}({message})\n") == [], topic

    @pytest.mark.parametrize("method", INFO_AND_ABOVE)
    @pytest.mark.parametrize(
        ("topic", "message", "expected_detail"),
        [
            ("a snake_case word", '"The needs_inference flag was turned off"', "the message holds the identifier `needs_inference`"),
            ("an environment variable", '"PIPELEX_API_KEY is not set"', "the message holds the identifier `PIPELEX_API_KEY`"),
            ("a leading underscore", '"A stuff name starts with _private"', "the message holds the identifier `_private`"),
            ("a call", '"The library was loaded before setup()"', "the message holds the call `setup()`"),
            ("a dotted call", '"Loader.load() was called twice"', "the message holds the call `Loader.load()`"),
        ],
    )
    def test_an_identifier_is_refused_at_info_and_above(self, method: str, topic: str, message: str, expected_detail: str) -> None:
        assert _details(f"def load():\n    log.{method}({message})\n", rule=LogCallRule.IDENTIFIER) == [expected_detail], topic

    @pytest.mark.parametrize("method", INFO_AND_ABOVE)
    @pytest.mark.parametrize(
        ("topic", "message"),
        [
            ("a word of Pipelex's vocabulary", '"A PipeBatch ran with no items"'),
            ("a file name with no underscore", '"The METHODS.toml file was read"'),
            ("a plural in parentheses", '"The model(s) were loaded"'),
            ("a hyphenated word", '"A well-known backend was chosen"'),
        ],
    )
    def test_a_word_that_is_no_identifier_passes(self, method: str, topic: str, message: str) -> None:
        assert _offending(f"def load():\n    log.{method}({message})\n") == [], topic

    @pytest.mark.parametrize("method", INFO_AND_ABOVE)
    def test_a_message_longer_than_the_bound_is_refused_at_info_and_above(self, method: str) -> None:
        too_long = "A" + "a" * MAX_MESSAGE_LENGTH
        at_the_bound = "A" + "a" * (MAX_MESSAGE_LENGTH - 1)
        assert _details(f'def load():\n    log.{method}("{too_long}")\n', rule=LogCallRule.LENGTH) == [
            f"the message is {MAX_MESSAGE_LENGTH + 1} characters long, more than {MAX_MESSAGE_LENGTH}"
        ]
        assert _offending(f'def load():\n    log.{method}("{at_the_bound}")\n') == []

    def test_the_length_is_read_on_the_folded_text(self) -> None:
        """Two literals joined by a `+` reach the console as one text, so their lengths add up."""
        half = "A" + "a" * (MAX_MESSAGE_LENGTH // 2)
        assert _details(f'def load():\n    log.info("{half}" + "{half}")\n', rule=LogCallRule.LENGTH) == [
            f"the message is {2 * len(half)} characters long, more than {MAX_MESSAGE_LENGTH}"
        ]

    def test_the_length_of_an_f_string_counts_its_literal_text_alone(self) -> None:
        """A spliced value is at least empty, so a literal text past the bound is too long whatever the value."""
        literal_text = "A" + "a" * MAX_MESSAGE_LENGTH
        assert _details(f'def load(alias):\n    log.info(f"{literal_text}{{alias}}")\n', rule=LogCallRule.LENGTH) == [
            f"the message is at least {MAX_MESSAGE_LENGTH + 1} characters long, more than {MAX_MESSAGE_LENGTH}"
        ]
        short_text = "A" + "a" * (MAX_MESSAGE_LENGTH - 10)
        assert _details(f'def load(alias):\n    log.info(f"{short_text}{{alias}}")\n', rule=LogCallRule.LENGTH) == []

    @pytest.mark.parametrize("method", BELOW_INFO)
    @pytest.mark.parametrize(
        ("topic", "message"),
        [
            ("an identifier", '"The needs_inference flag was turned off"'),
            ("a call", '"The library was loaded before setup()"'),
            ("a long message", '"A' + "a" * MAX_MESSAGE_LENGTH + '"'),
        ],
    )
    def test_identifiers_and_length_are_not_held_below_info(self, method: str, topic: str, message: str) -> None:
        """A person at a terminal reads DEBUG and VERBOSE, where a message may name what the code names."""
        assert _offending(f"def load():\n    log.{method}({message})\n") == [], topic

    @pytest.mark.parametrize(
        ("topic", "body", "expected_rules"),
        [
            (
                "a conditional between a good and a bad literal",
                'log.debug("The library was loaded" if flag else "the library was skipped.")',
                [[LogCallRule.LOWERCASE_START, LogCallRule.TRAILING_PERIOD]],
            ),
            (
                "a name bound to a bad literal on one branch",
                'msg = "The library was loaded"\n    if flag:\n        msg = "Loading the library..."\n    log.info(msg)',
                [[LogCallRule.TRAILING_PERIOD]],
            ),
            ("a module constant", "log.warning(LOADED)", [[LogCallRule.LOWERCASE_START]]),
            ("a literal extended with +=", 'msg = "The library"\n    msg += " was loaded."\n    log.verbose(msg)', [[LogCallRule.TRAILING_PERIOD]]),
            ("an end folded across a +", 'log.debug("The library " + "was loaded.")', [[LogCallRule.TRAILING_PERIOD]]),
            ("a start folded across a +", 'log.debug("" + "loaded")', [[LogCallRule.LOWERCASE_START]]),
            ("a period before a value", 'log.debug("The library was loaded. " + str(flag))', []),
        ],
    )
    def test_every_text_a_message_can_reach_the_console_as_is_read(self, topic: str, body: str, expected_rules: list[list[LogCallRule]]) -> None:
        """A message is read through its bindings and its concatenations, and one text that breaks a rule is enough."""
        assert _rules(f'LOADED = "loaded the library"\n\ndef load(flag):\n    {body}\n') == expected_rules, topic

    def test_a_concatenation_past_the_fold_bound_keeps_each_side_s_start_and_end_apart(self) -> None:
        """Past the bound, each left text keeps its start and each right text its end, and neither joins the other."""
        nb_alternatives = 17
        left = " if flag else ".join(f'"left{index_alternative}"' for index_alternative in range(nb_alternatives))
        right = " if flag else ".join(f'"right{index_alternative}."' for index_alternative in range(nb_alternatives))
        body = f"def load(flag):\n    log.debug(({left}) + ({right}))\n"
        assert sorted(_details(body, rule=LogCallRule.LOWERCASE_START)) == sorted(
            f"the message starts with the lowercase `left{index_alternative}`" for index_alternative in range(nb_alternatives)
        )
        assert _details(body, rule=LogCallRule.TRAILING_PERIOD) == ["the message ends with `.`"]

    @pytest.mark.parametrize("keyword", ["title", "inline"])
    def test_a_title_is_worded_as_a_text_of_its_own(self, keyword: str) -> None:
        offending = _offending(f'def load():\n    log.info("The library was loaded", {keyword}="the_library.")\n')
        assert [(breach.rule, breach.detail) for call in offending for breach in call.breaches] == [
            (LogCallRule.LOWERCASE_START, f"`{keyword}=` starts with the lowercase `the_library.`"),
            (LogCallRule.TRAILING_PERIOD, f"`{keyword}=` ends with `.`"),
            (LogCallRule.IDENTIFIER, f"`{keyword}=` holds the identifier `the_library`"),
        ]

    def test_a_wording_rule_is_named_in_the_signature(self) -> None:
        offending = _offending('def load():\n    log.info("loaded the library.")\n')
        assert [call.signature for call in offending] == ["info: 'loaded the library.' [lowercase-start, trailing-period]"]

    def test_every_rule_names_a_remedy(self) -> None:
        assert all(rule.remedy for rule in LogCallRule)


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
