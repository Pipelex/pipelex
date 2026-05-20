from pipelex.core.bundles.pipelex_bundle_blueprint import StepRole
from pipelex.core.interpreter.interpreter import PipelexInterpreter
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestInterpreterPreliminaryText:
    def test_mthds_with_preliminary_text_elaborates_end_to_end(self) -> None:
        mthds_content = """domain = "test_pipes"
description = "MTHDS using structuring_method = preliminary_text"

[concept]
Foo = "A foo concept"

[pipe.make_foo]
type = "PipeLLM"
description = "Make a Foo via preliminary text"
inputs = { topic = "Text" }
output = "Foo"
prompt = "Talk about $topic"
structuring_method = "preliminary_text"
"""
        bundle = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)

        assert bundle.pipe is not None
        assert set(bundle.pipe.keys()) == {"make_foo", "make_foo__draft_text", "make_foo__structure"}

        wrapping = bundle.pipe["make_foo"]
        assert isinstance(wrapping, PipeSequenceBlueprint)
        assert len(wrapping.steps) == 2
        assert wrapping.steps[0].pipe == "make_foo__draft_text"
        assert wrapping.steps[0].result == "draft_text"
        assert wrapping.steps[1].pipe == "make_foo__structure"

        draft = bundle.pipe["make_foo__draft_text"]
        assert isinstance(draft, PipeLLMBlueprint)
        assert draft.output == "Text"
        assert draft.structuring_method is None
        assert draft.prompt == "Talk about $topic"

        structure = bundle.pipe["make_foo__structure"]
        assert isinstance(structure, PipeStructureBlueprint)
        assert structure.inputs == {"draft_text": "Text"}
        assert structure.output == "Foo"

        assert bundle.elaboration_metadata is not None
        assert bundle.elaboration_metadata["make_foo__draft_text"].step_role is StepRole.DRAFT_TEXT
        assert bundle.elaboration_metadata["make_foo__structure"].step_role is StepRole.STRUCTURE

    def test_mthds_without_preliminary_text_is_unchanged(self) -> None:
        mthds_content = """domain = "test_pipes"
description = "Regression: pipes without preliminary_text are untouched"

[concept]
Foo = "A foo concept"

[pipe.make_foo]
type = "PipeLLM"
description = "Make a Foo directly"
inputs = { topic = "Text" }
output = "Foo"
prompt = "Talk about $topic"
"""
        bundle = PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=mthds_content)
        assert bundle.pipe is not None
        assert set(bundle.pipe.keys()) == {"make_foo"}
        assert isinstance(bundle.pipe["make_foo"], PipeLLMBlueprint)
        assert bundle.elaboration_metadata is None
