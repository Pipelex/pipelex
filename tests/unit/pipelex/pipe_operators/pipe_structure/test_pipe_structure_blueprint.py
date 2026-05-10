import pytest

from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureBlueprint:
    def test_valid_single_input_text_compatible_and_structured_output(self):
        blueprint = PipeStructureBlueprint(
            description="Structure the text into a Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo",
        )
        assert blueprint.nb_inputs == 1
        assert blueprint.input_names == ["draft_text"]
        assert blueprint.output == "Foo"

    def test_valid_with_list_output(self):
        blueprint = PipeStructureBlueprint(
            description="Produce a list of Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo[]",
        )
        assert blueprint.output == "Foo[]"

    def test_valid_with_fixed_count_output(self):
        blueprint = PipeStructureBlueprint(
            description="Produce 3 Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo[3]",
        )
        assert blueprint.output == "Foo[3]"

    def test_rejects_native_text_output(self):
        with pytest.raises(ValueError, match="must be a structured concept"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"draft_text": "native.Text"},
                output="native.Text",
            )

    def test_rejects_bare_text_output(self):
        with pytest.raises(ValueError, match="must be a structured concept"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"draft_text": "native.Text"},
                output="Text",
            )

    def test_rejects_zero_inputs(self):
        with pytest.raises(ValueError, match="exactly one Text-compatible input"):
            PipeStructureBlueprint(
                description="Bad",
                inputs=None,
                output="Foo",
            )

    def test_rejects_multiple_inputs(self):
        with pytest.raises(ValueError, match="exactly one Text-compatible input"):
            PipeStructureBlueprint(
                description="Bad",
                inputs={"a": "native.Text", "b": "native.Text"},
                output="Foo",
            )
