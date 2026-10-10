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
            ("the facade from its own module under an alias", "from pipelex.tools.log.log import log as plog\n", 'plog.info(f"{alias}")'),
            ("the package imported", "import pipelex\n", 'pipelex.log.warning(f"{alias}")'),
            ("the package imported under an alias", "import pipelex as px\n", 'px.log.info(f"{alias}")'),
            ("the facade's module imported from its package", "from pipelex.tools.log import log as m\n", 'm.log.info(f"{alias}")'),
            ("the facade's module imported under an alias", "import pipelex.tools.log.log as x\n", 'x.log.info(f"{alias}")'),
            ("the facade's module imported by its full path", "import pipelex.tools.log.log\n", 'pipelex.tools.log.log.log.info(f"{alias}")'),
            ("a parent package imported", "from pipelex.tools import log as log_package\n", 'log_package.log.log.info(f"{alias}")'),
            ("a relative import of the facade", "from ..tools.log.log import log\n", 'log.info(f"{alias}")'),
            ("a relative import of the package's re-export", "from .. import log\n", 'log.info(f"{alias}")'),
            ("a star import from the package", "from pipelex import *\n", 'log.info(f"{alias}")'),
            ("an import inside the function", "", 'from pipelex import log as local_log\n    local_log.info(f"{alias}")'),
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
            ("the facade's module, not the facade", "from pipelex.tools.log import log\n", 'log.info(f"{alias}")'),
            ("another package's log", "from somewhere import log\n", 'log.info(f"{alias}")'),
        ],
    )
    def test_a_call_that_is_not_the_facade_s_is_not_read(self, topic: str, header: str, call: str) -> None:
        assert _offending(f"def load(self, alias):\n    {call}\n", header=header) == [], topic

    @pytest.mark.parametrize(
        ("topic", "header", "body", "expected"),
        [
            ("a parameter named like the facade", FACADE_IMPORT, 'def load(log, alias):\n    log.info(f"{alias}")\n', []),
            (
                "a local named like the facade",
                FACADE_IMPORT,
                'def load(alias):\n    log = logging.getLogger(__name__)\n    log.info(f"{alias}")\n',
                [],
            ),
            (
                "the facade imported in another function",
                "",
                'def setup():\n    from pipelex import log\n\ndef load(alias):\n    log.info(f"{alias}")\n',
                [],
            ),
            (
                "the facade imported in the same function",
                "",
                'def setup():\n    from pipelex import log\n    log.info(f"{__name__}")\n\ndef load(alias):\n    log.info(f"{alias}")\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "the facade imported in an enclosing function",
                "",
                'def load(alias):\n    from pipelex import log\n    def inner():\n        log.info(f"{alias}")\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "the facade imported after a function that calls it",
                "",
                'def load(alias):\n    log.info(f"{alias}")\n\nfrom pipelex import log\n',
                [[LogCallRule.F_STRING]],
            ),
        ],
    )
    def test_a_receiver_is_the_facade_where_a_facade_import_reaches_the_call(
        self, topic: str, header: str, body: str, expected: list[list[LogCallRule]]
    ) -> None:
        """The receiver's name is read in the call's own scope, by the same bindings a message is read through."""
        assert _rules(body, header=header) == expected, topic

    @pytest.mark.parametrize(
        ("topic", "call", "expected_details"),
        [
            ("an expanded message", 'log.warning(**{"content": f"Value {alias}"})', ["the message is an f-string"]),
            ("an expanded title", 'log.warning("Loaded", **{"title": f"Load of {alias}"})', ["`title=` is an f-string"]),
            ("an expanded inline title", 'log.warning("Loaded", **{"inline": f"Load of {alias}"})', ["`inline=` is an f-string"]),
            (
                "expanded markup below INFO",
                'log.debug(**{"content": "[red]Loaded[/red]"})',
                ["the message holds the markup tag `[red]`", "the message holds the markup tag `[/red]`"],
            ),
            ("an expanded literal with fields", 'log.info(**{"content": "Loaded", "fields": {"alias": alias}})', []),
        ],
    )
    def test_a_dict_literal_expanded_into_a_call_is_read_as_its_keywords(self, topic: str, call: str, expected_details: list[str]) -> None:
        offending = _offending(f"def load(alias):\n    {call}\n")
        assert [breach.detail for call_found in offending for breach in call_found.breaches] == expected_details, topic

    @pytest.mark.parametrize(
        ("topic", "call", "expected_detail"),
        [
            ("a mapping", "log.warning(**params)", "`**params` is an expansion whose keywords cannot be read"),
            ("a mapping below INFO", 'log.debug("Loaded", **params)', "`**params` is an expansion whose keywords cannot be read"),
            (
                "a dict literal with a computed key",
                'log.info(**{key: "Loaded"})',
                "`**{key: 'Loaded'}` is an expansion whose keywords cannot be read",
            ),
            (
                "a dict literal expanding another",
                'log.info(**{**params, "content": "Loaded"})',
                "`**{**params, 'content': 'Loaded'}` is an expansion whose keywords cannot be read",
            ),
        ],
    )
    def test_an_expansion_that_cannot_be_read_is_refused_at_every_level(self, topic: str, call: str, expected_detail: str) -> None:
        """A `**` the guard cannot read may carry the message or a title, so neither rule could be checked through it."""
        offending = _offending(f"def load(params, key):\n    {call}\n")
        assert [[(breach.rule, breach.detail) for breach in call_found.breaches] for call_found in offending] == [
            [(LogCallRule.NON_LITERAL, expected_detail)]
        ], topic

    def test_an_expansion_that_cannot_be_read_is_named_in_the_signature(self) -> None:
        offending = _offending("def load(params):\n    log.warning(**params)\n")
        assert [call.signature for call in offending] == ["warning: **params [non-literal]"]

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
        assert offending[0].signature == 'warning: f"Could not load \'{alias}\': {exc!r:>10}", title=f"Load of {alias}" [f-string]'

    @pytest.mark.parametrize(
        ("topic", "body", "expected_signature"),
        [
            (
                "a name bound to an f-string",
                'def load(alias):\n    msg = f"Loaded {alias}"\n    log.warning(msg)\n',
                'warning: msg [f-string] where msg = f"Loaded {alias}"',
            ),
            (
                "a name bound twice",
                'def load(alias, cached):\n    msg = f"Loaded {alias}"\n    if cached:\n        msg = f"Reused {alias}"\n    log.warning(msg)\n',
                'warning: msg [f-string] where msg = f"Loaded {alias}"; msg = f"Reused {alias}"',
            ),
            ("a parameter", "def load(msg):\n    log.info(msg)\n", "info: msg [non-literal] where msg = <parameter>"),
            (
                "a module constant read through a concatenation",
                'PREFIX = "Loaded "\n\ndef load(alias):\n    log.info(PREFIX + alias)\n',
                "info: PREFIX + alias [concatenation] where PREFIX = 'Loaded '; alias = <parameter>",
            ),
            (
                "a name captured from an enclosing function",
                'def load(alias):\n    msg = "Loaded"\n    def inner():\n        log.info(msg)\n',
                "info: msg [non-literal] where msg = <enclosing function>",
            ),
            (
                "a binding that cannot reach the call stays out",
                (
                    'def load(alias):\n    msg = f"Loaded {alias}"\n    log.warning(msg)\n'
                    '    msg = f"Could not load {alias}"\n    raise ValueError(msg)\n'
                ),
                'warning: msg [f-string] where msg = f"Loaded {alias}"',
            ),
            (
                "a name rebuilt from itself",
                'def load():\n    msg = "["\n    msg = msg + "red]Loaded"\n    log.debug(msg)\n',
                "debug: msg [markup] where msg = '['; msg = msg + 'red]Loaded'",
            ),
        ],
    )
    def test_a_named_message_s_signature_carries_its_bindings_and_its_rules(self, topic: str, body: str, expected_signature: str) -> None:
        """The bindings are source text, sorted, never a line: what the call logs is its identity."""
        assert [call.signature for call in _offending(body)] == [expected_signature], topic

    @pytest.mark.parametrize(
        ("topic", "before", "after"),
        [
            (
                "the bound f-string is reworded",
                'def load(alias):\n    msg = f"Loaded {alias}"\n    log.warning(msg)\n',
                'def load(alias):\n    msg = f"Loaded the dependency {alias}"\n    log.warning(msg)\n',
            ),
            (
                "the bound f-string gains markup",
                'def load(alias):\n    msg = f"Loaded {alias}"\n    log.warning(msg)\n',
                'def load(alias):\n    msg = f"[red]Loaded[/red] {alias}"\n    log.warning(msg)\n',
            ),
            (
                "a module constant the message concatenates gains markup",
                'PREFIX = "Loaded "\n\ndef load(alias):\n    log.info(PREFIX + alias)\n',
                'PREFIX = "[red]Loaded[/red] "\n\ndef load(alias):\n    log.info(PREFIX + alias)\n',
            ),
        ],
    )
    def test_editing_what_a_grandfathered_call_logs_changes_its_signature(self, topic: str, before: str, after: str) -> None:
        """The call's own source is unchanged, so only the bindings and the rules in its signature tell the exemption is spent."""
        before_calls = _offending(before)
        after_calls = _offending(after)
        assert len(before_calls) == len(after_calls) == 1, topic
        assert before_calls[0].signature != after_calls[0].signature, topic

    def test_new_markup_is_named_in_the_signature_s_rules(self) -> None:
        offending = _offending('PREFIX = "[red]Loaded[/red] "\n\ndef load(alias):\n    log.info(PREFIX + alias)\n')
        assert offending[0].signature == "info: PREFIX + alias [concatenation, markup] where PREFIX = '[red]Loaded[/red] '; alias = <parameter>"

    @pytest.mark.parametrize(
        ("topic", "body", "expected_tag"),
        [
            ("two literals", 'log.info("[" + "red]Loaded")', "[red]"),
            ("a named literal operand", 'log.info(OPENING + "red]Loaded")', "[red]"),
            ("a literal extended with +=", 'msg = "["\n    msg += "red]Loaded"\n    log.verbose(msg)', "[red]"),
            ("a conditional between literals", 'log.debug(("[" if flag else "(") + "red]Loaded")', "[red]"),
            ("an f-string's literal edge", 'log.debug("[" + f"red]Loaded {flag}")', "[red]"),
            ("a name rebuilt from itself", 'msg = "["\n    msg = msg + "red]Loaded"\n    log.debug(msg)', "[red]"),
        ],
    )
    def test_markup_split_across_a_concatenation_is_refused(self, topic: str, body: str, expected_tag: str) -> None:
        offending = _offending(f'OPENING = "["\n\ndef load(flag):\n    {body}\n')
        markup_details = [breach.detail for call in offending for breach in call.breaches if breach.rule == LogCallRule.MARKUP]
        assert markup_details == [f"the message holds the markup tag `{expected_tag}`"], topic

    def test_a_value_between_two_literals_keeps_their_brackets_apart(self) -> None:
        """The guard cannot read the value, so it never joins the texts around it into a tag."""
        assert _offending('def load(alias):\n    log.debug("[" + alias + "red]")\n') == []

    @pytest.mark.parametrize(
        ("topic", "body"),
        [
            ("a None title", 'log.info("Loaded", title=None)'),
            ("a None inline title", 'log.warning("Loaded", inline=None)'),
            ("a title that is None or a literal", 'log.info("Loaded", title=None if alias else "Library")'),
            ("a title bound to None or a literal", 'title = None\n    if alias:\n        title = "Library"\n    log.info("Loaded", title=title)'),
        ],
    )
    def test_a_title_that_is_statically_none_is_no_message(self, topic: str, body: str) -> None:
        assert _offending(f"def load(alias):\n    {body}\n") == [], topic

    def test_a_none_title_stays_out_of_the_signature(self) -> None:
        offending = _offending('def load(alias):\n    log.info(f"Loaded {alias}", title=None)\n')
        assert [call.signature for call in offending] == ['info: f"Loaded {alias}" [f-string]']

    def test_moving_a_call_down_its_function_keeps_its_signature_and_key(self) -> None:
        """Lines never enter the identity, so an edit above a call moves nothing in the baseline."""
        before = _offending('def load(alias):\n    log.info(f"Loaded {alias}")\n')
        after = _offending('def load(alias):\n    prepared = True\n    del prepared\n    log.info(f"Loaded {alias}")\n')
        assert [(call.key, call.signature) for call in before] == [(call.key, call.signature) for call in after]
        assert before[0].lineno != after[0].lineno
