from __future__ import annotations

import textwrap

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import (
    MODULE_SCOPE_NAME,
    LogCallRule,
    OffendingCall,
    find_markup_tags,
    find_offending_calls_in_source,
)

SAMPLE_PATH = "pipelex/core/sample_module.py"
FACADE_IMPORT = "from pipelex import log\n"


def _offending(body: str, *, header: str = FACADE_IMPORT) -> list[OffendingCall]:
    """The offending calls of a snippet, the facade imported at its top unless the header says otherwise."""
    return find_offending_calls_in_source(source=header + textwrap.dedent(body), relative_path=SAMPLE_PATH)


def _rules(body: str, *, header: str = FACADE_IMPORT) -> list[list[LogCallRule]]:
    """The rules each offending call of a snippet breaks, in source order."""
    return [[breach.rule for breach in call.breaches] for call in _offending(body, header=header)]


class TestLogCallGuard:
    @pytest.mark.parametrize("method", ["info", "warning", "error", "critical"])
    @pytest.mark.parametrize(
        ("topic", "message", "expected_rule"),
        [
            ("an f-string with a placeholder", 'f"Loaded {alias}"', LogCallRule.F_STRING),
            ("a percent format", '"Loaded %s" % alias', LogCallRule.PERCENT_FORMAT),
            ("a concatenation with a value", '"Loaded " + alias', LogCallRule.CONCATENATION),
            ("a .format() call", '"Loaded {}".format(alias)', LogCallRule.FORMAT_CALL),
            ("an attribute", "self.message", LogCallRule.NON_LITERAL),
            ("a call's result", "describe(alias)", LogCallRule.NON_LITERAL),
            ("a mapping", '{"alias": alias}', LogCallRule.NON_LITERAL),
        ],
    )
    def test_an_interpolated_or_non_literal_message_is_refused_at_info_and_above(
        self, method: str, topic: str, message: str, expected_rule: LogCallRule
    ) -> None:
        """Each form a message can be built in is refused under its own name, on every method at INFO and above."""
        assert _rules(f"def load(alias, self, describe):\n    log.{method}({message})\n") == [[expected_rule]], topic

    @pytest.mark.parametrize(
        ("topic", "body"),
        [
            ("a string constant", 'log.warning("A dependency holds no valid bundle", fields={"dependency_alias": alias})\n'),
            ("an implicit concatenation", 'log.info("A long message " "split in two")\n'),
            ("an f-string without a placeholder", 'log.error(f"A run failed", include_exception=True)\n'),
            ("a + between literals", 'log.info("A long message " + "split in two")\n'),
            ("a conditional between literals", 'log.info("Hosted" if alias else "Local")\n'),
            ("a literal passed as content=", 'log.info(content="Loaded the library")\n'),
            ("a literal title", 'log.info("Loaded", title="Library")\n'),
        ],
    )
    def test_a_literal_message_passes(self, topic: str, body: str) -> None:
        assert _offending(f"def load(alias):\n    {body}") == [], topic

    @pytest.mark.parametrize("method", ["debug", "verbose"])
    def test_debug_and_verbose_may_keep_an_f_string(self, method: str) -> None:
        assert _offending(f'def load(alias):\n    log.{method}(f"Loaded {{alias}}", title=f"Load of {{alias}}")\n') == []

    def test_a_name_bound_to_an_f_string_is_refused_as_one_naming_the_binding_line(self) -> None:
        offending = _offending(
            """
            def load(alias):
                msg = f"Loaded {alias}"
                log.warning(msg)
            """
        )
        assert [[breach.rule for breach in call.breaches] for call in offending] == [[LogCallRule.F_STRING]]
        assert offending[0].breaches[0].detail == "the message is `msg`, bound at line 4 to an f-string"

    @pytest.mark.parametrize(
        ("topic", "body", "expected"),
        [
            ("a local literal", 'def load():\n    msg = "Loaded"\n    log.info(msg)\n', []),
            ("a module-level constant", 'LOADED_MESSAGE = "Loaded"\n\ndef load():\n    log.info(LOADED_MESSAGE)\n', []),
            ("a literal built from a module constant", 'PREFIX = "Loaded"\n\ndef load():\n    log.info(PREFIX + " the library")\n', []),
            ("a parameter", "def load(msg):\n    log.info(msg)\n", [[LogCallRule.NON_LITERAL]]),
            ("an unbound name", "def load():\n    log.info(msg)\n", [[LogCallRule.NON_LITERAL]]),
            ("a loop variable", 'def load():\n    for msg in ["a", "b"]:\n        log.info(msg)\n', [[LogCallRule.NON_LITERAL]]),
            (
                "a name extended with +=",
                'def load(alias):\n    msg = "Loaded "\n    msg += alias\n    log.info(msg)\n',
                [[LogCallRule.CONCATENATION]],
            ),
            ("a name bound to a call", "def load(alias):\n    msg = describe(alias)\n    log.info(msg)\n", [[LogCallRule.NON_LITERAL]]),
            (
                "a name bound in another function is not this one's",
                'def other():\n    msg = "Loaded"\n\ndef load():\n    log.info(msg)\n',
                [[LogCallRule.NON_LITERAL]],
            ),
        ],
    )
    def test_a_named_message_is_read_through_its_bindings(self, topic: str, body: str, expected: list[list[LogCallRule]]) -> None:
        assert _rules(body) == expected, topic

    @pytest.mark.parametrize("keyword", ["title", "inline"])
    def test_an_interpolated_title_is_refused_at_info_and_above(self, keyword: str) -> None:
        offending = _offending(f'def load(alias):\n    log.warning("Loaded", {keyword}=f"Load of {{alias}}")\n')
        assert [[breach.rule for breach in call.breaches] for call in offending] == [[LogCallRule.F_STRING]]
        assert offending[0].breaches[0].detail == f"`{keyword}=` is an f-string"

    @pytest.mark.parametrize("method", ["verbose", "debug", "info", "warning", "error", "critical"])
    @pytest.mark.parametrize(
        ("topic", "message", "expected_tag"),
        [
            ("an opening and a closing tag", '"[red]compose_company[/red] runs"', "[red]"),
            ("a compound style", '"[bold green]Company[/bold green]"', "[bold green]"),
            ("a bare closing tag", '"Done[/]"', "[/]"),
            ("a link", '"See [link=https://pipelex.com]the docs[/link]"', "[link=https://pipelex.com]"),
            ("an @ handler", '"Click [@click=app.bell]here[/]"', "[@click=app.bell]"),
            ("a theme style name", '"[repr.number]7[/repr.number]"', "[repr.number]"),
        ],
    )
    def test_a_markup_tag_in_a_literal_message_is_refused_at_every_level(self, method: str, topic: str, message: str, expected_tag: str) -> None:
        offending = _offending(f"def load():\n    log.{method}({message})\n")
        assert len(offending) == 1, topic
        markup_details = [breach.detail for breach in offending[0].breaches if breach.rule == LogCallRule.MARKUP]
        assert markup_details[0] == f"the message holds the markup tag `{expected_tag}`"

    def test_markup_in_the_literal_parts_of_a_debug_f_string_is_refused(self) -> None:
        """An f-string is allowed below INFO, its markup is not."""
        assert _rules('def load(alias):\n    log.debug(f"[red]{alias}[/red]")\n') == [[LogCallRule.MARKUP, LogCallRule.MARKUP]]

    def test_markup_in_a_title_is_refused_below_info(self) -> None:
        offending = _offending('def load():\n    log.verbose("Loaded", title="[bold]Library[/bold]")\n')
        assert offending[0].breaches[0].detail == "`title=` holds the markup tag `[bold]`"

    def test_markup_a_name_is_bound_to_is_refused(self) -> None:
        assert _rules('def load():\n    msg = "[red]Loaded[/red]"\n    log.verbose(msg)\n') == [[LogCallRule.MARKUP, LogCallRule.MARKUP]]

    @pytest.mark.parametrize(
        ("topic", "text"),
        [
            ("a type subscript", "expected list[int], got dict[str, Any]"),
            ("an errno", "[Errno 2] No such file or directory"),
            ("an index that is no style", "items[index] is missing"),
            ("an escaped tag", "\\[red] stays literal"),
            ("no bracket", "Loaded the library"),
        ],
    )
    def test_brackets_that_are_no_markup_pass(self, topic: str, text: str) -> None:
        assert find_markup_tags(text=text) == [], topic

    def test_a_call_breaking_both_rules_is_one_offending_call(self) -> None:
        assert _rules('def load(alias):\n    log.info(f"[red]{alias}[/red]")\n') == [[LogCallRule.F_STRING, LogCallRule.MARKUP, LogCallRule.MARKUP]]

    @pytest.mark.parametrize(
        ("topic", "header", "call"),
        [
            ("the facade from its own module", "from pipelex.tools.log.log import log\n", 'log.info(f"{alias}")'),
            ("the facade under an alias", "from pipelex import log as pipelex_log\n", 'pipelex_log.info(f"{alias}")'),
        ],
    )
    def test_the_facade_is_found_under_the_name_it_is_imported_as(self, topic: str, header: str, call: str) -> None:
        assert _rules(f"def load(alias):\n    {call}\n", header=header) == [[LogCallRule.F_STRING]], topic

    @pytest.mark.parametrize(
        ("topic", "header", "call"),
        [
            ("a stdlib logger", "import logging\n", 'logging.getLogger(__name__).info(f"{alias}")'),
            ("a logger attribute", "", 'self._logger.warning(f"{alias}")'),
            ("a log the module never imported from pipelex", "", 'log.info(f"{alias}")'),
            ("a facade method that does not log", FACADE_IMPORT, 'log.context(request_id=f"{alias}")'),
        ],
    )
    def test_a_call_that_is_not_the_facade_s_is_not_read(self, topic: str, header: str, call: str) -> None:
        assert _offending(f"def load(self, alias):\n    {call}\n", header=header) == [], topic

    @pytest.mark.parametrize(
        ("topic", "body", "expected_qualified_name"),
        [
            ("a module-level call", 'log.info(f"{ALIAS}")\n', MODULE_SCOPE_NAME),
            ("a function", 'def load(alias):\n    log.info(f"{alias}")\n', "load"),
            ("a method", 'class Loader:\n    def load(self, alias):\n        log.info(f"{alias}")\n', "Loader.load"),
            ("a nested function", 'def load():\n    def inner(alias):\n        log.info(f"{alias}")\n', "load.inner"),
            (
                "a class inside a function",
                'def load():\n    class Local:\n        def run(self, alias):\n            log.info(f"{alias}")\n',
                "load.Local.run",
            ),
        ],
    )
    def test_a_call_is_keyed_by_its_file_and_enclosing_qualified_name(self, topic: str, body: str, expected_qualified_name: str) -> None:
        offending = _offending(body)
        assert [call.key for call in offending] == [f"{SAMPLE_PATH}::{expected_qualified_name}"], topic

    def test_the_signature_is_the_method_and_the_message_source_never_a_line(self) -> None:
        offending = _offending(
            """
            def load(alias, exc):
                log.warning(
                    f"Could not load '{alias}': {exc!r:>10}",
                    title=f"Load of {alias}",
                )
            """
        )
        assert offending[0].signature == 'warning: f"Could not load \'{alias}\': {exc!r:>10}", title=f"Load of {alias}"'

    def test_moving_a_call_down_its_function_keeps_its_signature_and_key(self) -> None:
        """Lines never enter the identity, so an edit above a call moves nothing in the baseline."""
        before = _offending('def load(alias):\n    log.info(f"Loaded {alias}")\n')
        after = _offending('def load(alias):\n    prepared = True\n    del prepared\n    log.info(f"Loaded {alias}")\n')
        assert [(call.key, call.signature) for call in before] == [(call.key, call.signature) for call in after]
        assert before[0].lineno != after[0].lineno
