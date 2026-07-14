import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint
from tests.unit.pipelex.pipe_operators.pipe_extract.data import PipeExtractInputTestCases


class TestPipeExtractBlueprint:
    @pytest.mark.parametrize(("test_id", "blueprint"), PipeExtractInputTestCases.VALID_CASES)
    def test_valid_blueprints(self, test_id: str, blueprint: PipeExtractBlueprint):
        assert blueprint.nb_inputs == 1, f"Expected exactly one input for {test_id}"
        assert blueprint.output == "native.Page[]", f"Unexpected output for {test_id}"

    @pytest.mark.parametrize(
        "output",
        [
            "Page[]",  # authoring spelling
            "native.Page[]",  # normalized spelling, as rewritten by crate normalization
        ],
    )
    def test_validate_output_accepts_both_spellings(self, output: str):
        """The validator must accept the normalized ref as well as the authored one: crate
        normalization qualifies `Page[]` to `native.Page[]` and then rebuilds the blueprints, which
        re-runs this validator on its own output.
        """
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"document": "Document"},
            output=output,
        )
        assert blueprint.output == output

    @pytest.mark.parametrize(
        "output",
        [
            "Page",  # missing multiplicity: extract always emits a list
            "native.Page",
            "Page[3]",  # fixed count: page count is data-dependent
            "Text[]",  # wrong concept
            "native.Text[]",
            "intake.Page[]",  # a domain concept named Page is not the native Page
        ],
    )
    def test_validate_output_rejects_anything_but_a_native_page_list(self, output: str):
        with pytest.raises(ValidationError) as exc_info:
            PipeExtractBlueprint(
                description="lorem ipsum",
                inputs={"document": "Document"},
                output=output,
            )
        assert "PipeExtract output must be 'Page[]'" in str(exc_info.value)

    @pytest.mark.parametrize(
        "inputs",
        [
            {"document": "Document"},
            {"image": "Image"},
        ],
    )
    def test_validate_inputs_correct(self, inputs: dict[str, str]):
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs=inputs,
            output="Page[]",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == list(inputs)

    def test_validate_inputs_incorrect(self):
        with pytest.raises(ValidationError) as exc_info:
            PipeExtractBlueprint(
                description="lorem ipsum",
                inputs={},
                output="Page[]",
            )
        assert "Missing input provided for PipeExtract" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            PipeExtractBlueprint(
                description="lorem ipsum",
                inputs={"doc1": "Document", "doc2": "Document"},
                output="Page[]",
            )
        assert "Too many inputs provided for PipeExtract" in str(exc_info.value)
