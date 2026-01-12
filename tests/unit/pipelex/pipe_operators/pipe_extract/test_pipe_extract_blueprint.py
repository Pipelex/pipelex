import pytest
from pydantic import ValidationError

from pipelex.pipe_operators.extract.pipe_extract_blueprint import PipeExtractBlueprint


class TestPipeExtractBlueprint:
    def test_force_output_correct(self):
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"document": "Document"},
            output="Page[]",
        )
        assert blueprint.output == "Page[]"

        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"image": "Image"},
            output="Page[]",
        )
        assert blueprint.output == "Page[]"

    def test_validate_inputs_correct(self):
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"document": "Document"},
            output="Page[]",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["document"]

        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"image": "Image"},
            output="Page[]",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["image"]

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

    def test_validate_output_correct(self):
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"document": "Document"},
            output="Page[]",
        )
        assert blueprint.output == "Page[]"

    def test_validate_output_incorrect(self):
        blueprint = PipeExtractBlueprint(
            description="lorem ipsum",
            inputs={"document": "Document"},
            output="Page[]",
        )
        assert blueprint.output == "Page[]"
