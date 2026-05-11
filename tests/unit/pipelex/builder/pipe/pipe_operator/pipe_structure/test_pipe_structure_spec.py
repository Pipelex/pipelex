import pytest

from pipelex.builder.pipe.pipe_structure_spec import PipeStructureSpec
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureSpec:
    def test_spec_to_blueprint_minimal(self):
        spec = PipeStructureSpec(
            pipe_code="extract_book_info",
            pipe_category="PipeOperator",
            description="Turn raw text into a Book record",
            inputs={"draft_text": "Text"},
            output="Book",
        )
        blueprint = spec.to_blueprint()
        assert isinstance(blueprint, PipeStructureBlueprint)
        assert blueprint.description == "Turn raw text into a Book record"
        assert blueprint.inputs == {"draft_text": "Text"}
        assert blueprint.output == "Book"
        assert blueprint.model is None

    def test_spec_to_blueprint_with_model(self):
        spec = PipeStructureSpec(
            pipe_code="structure_doc",
            pipe_category="PipeOperator",
            description="Structure document text",
            inputs={"page_text": "Text"},
            output="ContactCard[]",
            model="some-model-handle",
        )
        blueprint = spec.to_blueprint()
        assert blueprint.model is not None
        assert blueprint.output == "ContactCard[]"

    def test_spec_rejects_empty_model(self):
        with pytest.raises(ValueError, match="Model cannot be an empty string"):
            PipeStructureSpec(
                pipe_code="structure_doc",
                pipe_category="PipeOperator",
                description="Bad",
                inputs={"page_text": "Text"},
                output="ContactCard",
                model="   ",
            )
