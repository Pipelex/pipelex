from __future__ import annotations

import ast
import textwrap
from typing import TYPE_CHECKING

import pytest

from pipelex.cli.dev_cli.commands.log_call_guard import LogCallRule, OffendingCall, find_offending_calls_in_source

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

SAMPLE_PATH = "pipelex/core/sample_module.py"

#: The facade, and a module-level literal that a name resolving to the wrong scope would wrongly pass as.
HEADER = 'from pipelex import log\n\nMSG = "A fixed message"\n\n'


def _offending(body: str) -> list[OffendingCall]:
    return find_offending_calls_in_source(source=HEADER + textwrap.dedent(body), relative_path=SAMPLE_PATH)


def _rules(body: str) -> list[list[LogCallRule]]:
    return [[breach.rule for breach in call.breaches] for call in _offending(body)]


class TestLogCallGuardScopes:
    def test_a_name_bound_in_an_enclosing_function_is_captured_never_the_module_s_literal(self) -> None:
        offending = _offending(
            """
            def outer(alias):
                MSG = f"Loaded {alias}"
                def inner():
                    log.info(MSG)
            """
        )
        assert [[breach.rule for breach in call.breaches] for call in offending] == [[LogCallRule.NON_LITERAL]]
        assert offending[0].breaches[0].detail == "the message is `MSG`, captured from an enclosing function"

    @pytest.mark.parametrize(
        ("topic", "body", "expected"),
        [
            ("a module literal read from a method", "class Loader:\n    def load(self):\n        log.info(MSG)\n", []),
            (
                "a class attribute is no enclosing scope of a method",
                'class Loader:\n    MSG = f"{__name__}"\n    def load(self):\n        log.info(MSG)\n',
                [],
            ),
            (
                "a call in a class body reads the class's names",
                'class Loader:\n    MSG = f"{__name__}"\n    log.info(MSG)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a lambda's free name is captured from its enclosing function",
                'def load(alias):\n    MSG = "Loaded"\n    return lambda: log.info(MSG)\n',
                [[LogCallRule.NON_LITERAL]],
            ),
            (
                "a comprehension reads as part of the function it is written in",
                'def load(items):\n    message = "Loaded"\n    return [log.info(message) for _item in items]\n',
                [],
            ),
            (
                "a global assignment in a function rebinds the module's name",
                'def reset(alias):\n    global MSG\n    MSG = f"Loaded {alias}"\n\ndef load():\n    log.info(MSG)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a nonlocal assignment rebinds the enclosing function's name",
                (
                    'def load(alias):\n    message = "Loaded"\n    def reset():\n        nonlocal message\n'
                    '        message = f"Loaded {alias}"\n    log.info(message)\n'
                ),
                [[LogCallRule.F_STRING]],
            ),
        ],
    )
    def test_a_name_resolves_by_python_s_scoping(self, topic: str, body: str, expected: list[list[LogCallRule]]) -> None:
        assert _rules(body) == expected, topic

    @pytest.mark.parametrize(
        ("topic", "body", "expected_rule"),
        [
            ("a list comprehension target", "def load(items):\n    return [log.info(MSG) for MSG in items]\n", LogCallRule.NON_LITERAL),
            ("a set comprehension target", "def load(items):\n    return {log.info(MSG) for MSG in items}\n", LogCallRule.NON_LITERAL),
            ("a generator target", "def load(items):\n    return list(log.info(MSG) for MSG in items)\n", LogCallRule.NON_LITERAL),
            ("a dict comprehension target", "def load(items):\n    return {MSG: log.info(MSG) for MSG in items}\n", LogCallRule.NON_LITERAL),
            ("a match capture", "def load(subject):\n    match subject:\n        case MSG:\n            log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("a match star", "def load(subject):\n    match subject:\n        case [*MSG]:\n            log.info(MSG)\n", LogCallRule.NON_LITERAL),
            (
                "a match mapping rest",
                "def load(subject):\n    match subject:\n        case {**MSG}:\n            log.info(MSG)\n",
                LogCallRule.NON_LITERAL,
            ),
            ("a lambda parameter", "handler = lambda MSG: log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("a function parameter", "def load(MSG):\n    log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("a walrus", 'def load(alias):\n    if (MSG := f"Loaded {alias}"):\n        log.info(MSG)\n', LogCallRule.F_STRING),
            (
                "a walrus in a comprehension binds in its function",
                'def load(items):\n    _ = [(MSG := f"Loaded {item}") for item in items]\n    log.info(MSG)\n',
                LogCallRule.F_STRING,
            ),
            ("a for target", "def load(items):\n    for MSG in items:\n        log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("a with target", "def load(path):\n    with open(path) as MSG:\n        log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("an import alias", "def load():\n    from somewhere import thing as MSG\n    log.info(MSG)\n", LogCallRule.NON_LITERAL),
            ("an unpacking", "def load(pair):\n    MSG, _other = pair\n    log.info(MSG)\n", LogCallRule.NON_LITERAL),
        ],
    )
    def test_every_binding_form_shadows_the_module_s_literal(self, topic: str, body: str, expected_rule: LogCallRule) -> None:
        assert _rules(body) == [[expected_rule]], topic

    def test_an_except_target_shadows_the_module_s_literal_and_is_the_exception_itself(self) -> None:
        """The name is no literal, and what it holds is the handled exception, which the message would carry as its text."""
        body = "def load(path):\n    try:\n        open(path)\n    except OSError as MSG:\n        log.info(MSG)\n"
        assert _rules(body) == [[LogCallRule.NON_LITERAL, LogCallRule.SPLICED_EXCEPTION]]

    @pytest.mark.parametrize(
        ("topic", "body"),
        [
            ("a subscript store", 'def load(cache):\n    msg = "Loaded"\n    cache[msg] = 1\n    log.info(msg)\n'),
            ("an attribute store", 'def load(alias):\n    msg = "Loaded"\n    msg.attr = alias\n    log.info(msg)\n'),
            ("an augmented subscript store", 'def load(counts):\n    msg = "Loaded"\n    counts[msg] += 1\n    log.info(msg)\n'),
        ],
    )
    def test_an_assignment_that_only_mentions_a_name_does_not_rebind_it(self, topic: str, body: str) -> None:
        assert _offending(body) == [], topic

    @pytest.mark.parametrize(
        ("topic", "body", "expected"),
        [
            ("a literal += a literal", 'def load():\n    msg = "Loaded"\n    msg += " the library"\n    log.info(msg)\n', []),
            ("a literal += a module literal", 'def load():\n    msg = "Loaded: "\n    msg += MSG\n    log.info(msg)\n', []),
            ("a literal built from itself", 'def load():\n    msg = "Loaded"\n    msg = msg + " the library"\n    log.info(msg)\n', []),
            ("a literal += a value", 'def load(alias):\n    msg = "Loaded "\n    msg += alias\n    log.info(msg)\n', [[LogCallRule.CONCATENATION]]),
            (
                "a literal %= a value",
                'def load(alias):\n    msg = "Loaded %s"\n    msg %= alias\n    log.info(msg)\n',
                [[LogCallRule.PERCENT_FORMAT]],
            ),
            ("a literal *= a count", 'def load(count):\n    msg = "Loaded"\n    msg *= count\n    log.info(msg)\n', [[LogCallRule.NON_LITERAL]]),
        ],
    )
    def test_an_augmented_assignment_is_read_by_its_operator_and_value(self, topic: str, body: str, expected: list[list[LogCallRule]]) -> None:
        assert _rules(body) == expected, topic

    @pytest.mark.parametrize(
        ("topic", "body", "expected"),
        [
            (
                "a binding after the call, before a raise",
                'def load(alias):\n    msg = "Loaded"\n    log.info(msg)\n    msg = f"Could not load {alias}"\n    raise ValueError(msg)\n',
                [],
            ),
            ("a binding replaced on straight-line code", 'def load(alias):\n    msg = f"{alias}"\n    msg = "Loaded"\n    log.info(msg)\n', []),
            (
                "a branch that raises brings nothing",
                (
                    'def load(alias):\n    msg = "Loaded"\n    if alias:\n'
                    '        msg = f"Bad {alias}"\n        raise ValueError(msg)\n    log.info(msg)\n'
                ),
                [],
            ),
            (
                "a branch that returns brings nothing",
                'def load(alias):\n    msg = "Loaded"\n    if alias:\n        msg = f"Bad {alias}"\n        return\n    log.info(msg)\n',
                [],
            ),
            (
                "either branch of an if",
                'def load(alias):\n    if alias:\n        msg = f"{alias}"\n    else:\n        msg = "Loaded"\n    log.info(msg)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "an if without an else keeps what came before",
                'def load(alias):\n    msg = f"{alias}"\n    if alias:\n        msg = "Loaded"\n    log.info(msg)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a handler sees what the try body bound",
                (
                    'def load(alias):\n    msg = "Loaded"\n    try:\n        msg = f"{alias}"\n'
                    "        open(alias)\n    except OSError:\n        log.info(msg)\n"
                ),
                [[LogCallRule.F_STRING]],
            ),
            (
                "a try body or its handler",
                'def load(alias):\n    try:\n        msg = f"{alias}"\n    except OSError:\n        msg = "Failed"\n    log.info(msg)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a match case",
                (
                    'def load(alias):\n    match alias:\n        case "x":\n            msg = f"{alias}"\n'
                    '        case _:\n            msg = "Loaded"\n    log.info(msg)\n'
                ),
                [[LogCallRule.F_STRING]],
            ),
            (
                "a binding later in a loop reaches an earlier read",
                'def load(items):\n    msg = "Loaded"\n    for item in items:\n        log.info(msg)\n        msg = f"{item}"\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a binding after a loop does not reach a read in it",
                (
                    'def load(items, alias):\n    msg = "Loaded"\n    for item in items:\n'
                    '        log.info(msg)\n    msg = f"{alias}"\n    raise ValueError(msg)\n'
                ),
                [],
            ),
            (
                "a break leaves the loop with what it bound",
                'def load(alias):\n    msg = "Loaded"\n    while alias:\n        msg = f"{alias}"\n        break\n    log.info(msg)\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a module name rebound once a function exists reaches its calls",
                'TEXT = "Loaded"\n\ndef load():\n    log.info(TEXT)\n\nTEXT = f"Loaded {__name__}"\n',
                [[LogCallRule.F_STRING]],
            ),
            (
                "a module name replaced before a function exists does not",
                'TEXT = f"Loaded {__name__}"\nTEXT = "Loaded"\n\ndef load():\n    log.info(TEXT)\n',
                [],
            ),
            (
                "a module-level call reads the module's flow",
                'TEXT = "Loaded"\nlog.info(TEXT)\nTEXT = f"Loaded {__name__}"\n',
                [],
            ),
        ],
    )
    def test_only_the_bindings_that_can_reach_a_read_are_read(self, topic: str, body: str, expected: list[list[LogCallRule]]) -> None:
        """A binding counts when some path of the control flow carries it to the read, and never otherwise."""
        assert _rules(body) == expected, topic

    def test_each_scope_is_indexed_once_however_many_calls_read_it(self, mocker: MockerFixture) -> None:
        """The walk grows with the module, not with the module times its calls: a lookup reads an index, never the scope again."""

        def nodes_walked(*, nb_functions: int) -> int:
            # A module-level statement beside each function, so a walk of the module per lookup costs what the module holds.
            functions = "".join(
                f"VALUE_{index_function} = {index_function}\n\ndef load_{index_function}():\n    log.info(MSG)\n\n"
                for index_function in range(nb_functions)
            )
            spy = mocker.spy(ast, "iter_child_nodes")
            find_offending_calls_in_source(source=HEADER + functions, relative_path=SAMPLE_PATH)
            count = spy.call_count
            mocker.stop(spy)
            return count

        small = nodes_walked(nb_functions=10)
        large = nodes_walked(nb_functions=80)
        # Eight times the functions: a linear walk is about eight times longer, a walk per lookup about sixty-four.
        assert large <= 10 * small
