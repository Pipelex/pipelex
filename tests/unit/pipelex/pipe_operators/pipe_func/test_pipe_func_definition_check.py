import pytest

from pipelex.pipe_operators.func.pipe_func_definition_check import pipe_func_definition_violation

_HEADER = "from pipelex.system.registries.func_registry import pipe_func\n\n\n"

_BODY = "(working_memory):\n    return working_memory\n"

_INDENTED_BODY = "(working_memory):\n        return working_memory\n"


class TestPipeFuncDefinitionCheck:
    @pytest.mark.parametrize(
        "source",
        [
            pytest.param(f"{_HEADER}@pipe_func()\ndef compute_totals{_BODY}", id="def"),
            pytest.param(f"{_HEADER}@pipe_func()\nasync def compute_totals{_BODY}", id="async-def"),
            pytest.param(
                f"from pipelex.system.registries.func_registry import pipe_func as marker\n\n\n@marker()\ndef compute_totals{_BODY}", id="aliased"
            ),
            pytest.param(
                f"from pipelex.system.registries import func_registry\n\n\n@func_registry.pipe_func()\ndef compute_totals{_BODY}", id="module-import"
            ),
            pytest.param(f"import pipelex.system.registries.func_registry as reg\n\n\n@reg.pipe_func()\ndef compute_totals{_BODY}", id="import-as"),
            pytest.param(
                f"import functools\n{_HEADER}@functools.cache\n@pipe_func()\ndef compute_totals{_BODY}",
                id="among-other-decorators",
            ),
        ],
    )
    def test_a_marked_top_level_function_is_proven(self, source: str) -> None:
        assert pipe_func_definition_violation(source=source, function="compute_totals", module_label="funcs/totals.py") is None

    @pytest.mark.parametrize(
        ("source", "expected_message"),
        [
            pytest.param("def broken(:\n", "does not parse as Python", id="syntax-error"),
            pytest.param(f"{_HEADER}@pipe_func()\ndef other{_BODY}", "defines no top-level function 'compute_totals'", id="missing"),
            pytest.param(f"{_HEADER}def compute_totals{_BODY}", "is not decorated with @pipe_func()", id="unmarked"),
            pytest.param(f"{_HEADER}@pipe_func\ndef compute_totals{_BODY}", "without parentheses", id="marker-without-parentheses"),
            pytest.param(f'{_HEADER}@pipe_func(name="totals")\ndef compute_totals{_BODY}', "passes arguments to @pipe_func()", id="marker-name"),
            pytest.param(
                f"{_HEADER}@pipe_func()\ndef compute_totals{_BODY}\n\n@pipe_func()\ndef compute_totals{_BODY}",
                "more than once",
                id="defined-twice",
            ),
            pytest.param(f"{_HEADER}from funcs.impl import compute_totals\n", "an import, which re-exports", id="re-export"),
            pytest.param(f"{_HEADER}compute_totals = len\n", "an assignment", id="assignment"),
            pytest.param(f"{_HEADER}class compute_totals:\n    pass\n", "a class definition", id="class"),
            pytest.param(
                f"{_HEADER}import sys\nif sys.platform:\n    @pipe_func()\n    def compute_totals{_INDENTED_BODY}",
                "under a condition",
                id="conditional-definition",
            ),
            pytest.param(
                f"from somewhere_else import pipe_func\n\n\n@pipe_func()\ndef compute_totals{_BODY}", "is not decorated", id="foreign-marker"
            ),
        ],
    )
    def test_what_cannot_be_proven_is_refused_naming_the_module(self, source: str, expected_message: str) -> None:
        violation = pipe_func_definition_violation(source=source, function="compute_totals", module_label="funcs/totals.py")

        assert violation is not None
        assert expected_message in violation
        assert "funcs/totals.py" in violation
