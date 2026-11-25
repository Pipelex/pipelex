"""`escape_py_string`: a string as the Python literal `ruff format` leaves alone."""

import ast
import random

import pytest

from pipelex.tools.misc.python_literals import escape_py_string
from tests.unit.pipelex.tools.misc.cases import PythonLiteralsCases


class TestEscapePyString:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            pytest.param("plain", '"plain"', id="plain"),
            pytest.param("it's", '"it\'s"', id="single-quote"),
            pytest.param('say "hi"', "'say \"hi\"'", id="double-quotes"),
            pytest.param("'a' \"b\"", '"\'a\' \\"b\\""', id="tied-quotes"),
            pytest.param("back\\slash\nnewline", '"back\\\\slash\\nnewline"', id="backslash-and-newline"),
        ],
    )
    def test_escapes_as_ruff_leaves_it(self, value: str, expected: str):
        assert escape_py_string(value) == expected

    def test_randomized_values_evaluate_back_to_themselves(self):
        generator = random.Random(20261116)
        for _ in range(3000):
            value = "".join(generator.choice(PythonLiteralsCases.RANDOM_ALPHABET) for _ in range(generator.randint(0, 24)))
            literal = escape_py_string(value)
            assert ast.literal_eval(literal) == value, repr(value)
            assert literal[0] == ("'" if value.count("'") < value.count('"') else '"')
