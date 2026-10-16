import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.func.function_name import FunctionImportPath, split_function_name
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint


def _blueprint(*, function_name: str) -> PipeFuncBlueprint:
    return PipeFuncBlueprint(description="Compute the totals", inputs={}, output="Text", function_name=function_name)


class TestPipeFuncBlueprint:
    @pytest.mark.parametrize(
        ("function_name", "expected"),
        [
            pytest.param("totals.compute_totals", FunctionImportPath(module_name="totals", function="compute_totals"), id="module-at-the-root"),
            pytest.param(
                "funcs.totals.compute_totals", FunctionImportPath(module_name="funcs.totals", function="compute_totals"), id="module-in-a-package"
            ),
            pytest.param("fonctions.résumé.calculer", FunctionImportPath(module_name="fonctions.résumé", function="calculer"), id="non-ascii"),
        ],
    )
    def test_an_import_path_is_split_at_its_last_dot(self, function_name: str, expected: FunctionImportPath) -> None:
        assert _blueprint(function_name=function_name).function_name == function_name
        assert split_function_name(function_name=function_name) == expected

    def test_a_decomposed_name_is_read_in_nfc(self) -> None:
        decomposed = "fonctions.résumé.calculer"

        assert split_function_name(function_name=decomposed) == FunctionImportPath(module_name="fonctions.résumé", function="calculer")

    @pytest.mark.parametrize(
        ("function_name", "expected_message"),
        [
            pytest.param("compute_totals", "holds no dot, so it names no module", id="flat-name"),
            pytest.param("funcs..compute_totals", "holds the segment ''", id="empty-segment"),
            pytest.param("funcs.class.compute_totals", "holds the segment 'class'", id="keyword"),
            pytest.param("my-funcs.compute_totals", "holds the segment 'my-funcs'", id="not-an-identifier"),
            pytest.param("funcs.ﬁve.compute_totals", "changes under NFKC normalization", id="ligature"),
        ],
    )
    def test_a_name_that_is_not_an_import_path_is_refused_as_the_bundle_is_read(self, function_name: str, expected_message: str) -> None:
        with pytest.raises(ValidationError, match=expected_message):
            _blueprint(function_name=function_name)

    def test_a_flat_name_is_refused_with_the_migration_command(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            _blueprint(function_name="compute_totals")

        message = str(exc_info.value)
        assert "pipelex fix function-names <method folder>" in message
        assert "'funcs.totals.compute_totals'" in message
