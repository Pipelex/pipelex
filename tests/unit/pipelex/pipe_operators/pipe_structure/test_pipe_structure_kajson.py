from kajson import kajson

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.interpreter.bundle_elaborator import BundleElaborator
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestPipeStructureKajsonRoundtrip:
    def test_pipe_structure_blueprint_roundtrips(self) -> None:
        original = PipeStructureBlueprint(
            description="Structure draft text into a Foo",
            inputs={"draft_text": "native.Text"},
            output="Foo[]",
        )
        serialized = kajson.dumps(original)  # pyright: ignore[reportUnknownMemberType]
        deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]

        assert isinstance(deserialized, PipeStructureBlueprint)
        assert deserialized == original
        assert deserialized.inputs == {"draft_text": "native.Text"}
        assert deserialized.output == "Foo[]"

    def test_pipe_llm_blueprint_with_preliminary_text_roundtrips(self) -> None:
        original = PipeLLMBlueprint(
            type="PipeLLM",
            description="Make a Foo",
            inputs={"topic": "Text"},
            output="Foo",
            prompt="Talk about $topic",
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
        )
        serialized = kajson.dumps(original)  # pyright: ignore[reportUnknownMemberType]
        deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]

        assert isinstance(deserialized, PipeLLMBlueprint)
        assert deserialized == original
        assert deserialized.structuring_method is StructuringMethod.PRELIMINARY_TEXT

    def test_elaborated_bundle_pipes_roundtrip(self) -> None:
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Roundtrip the elaborated synthetic pipes",
            concept={"Foo": "A foo"},
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Make a Foo",
                    inputs={"topic": "Text"},
                    output="Foo",
                    prompt="Talk about $topic",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        for pipe_code, blueprint in elaborated.pipe.items():
            serialized = kajson.dumps(blueprint)  # pyright: ignore[reportUnknownMemberType]
            deserialized = kajson.loads(serialized)  # pyright: ignore[reportUnknownMemberType]
            assert deserialized == blueprint, f"Round-trip failed for synthetic pipe '{pipe_code}'"

        wrapping_serialized = kajson.dumps(elaborated.pipe["make_foo"])  # pyright: ignore[reportUnknownMemberType]
        wrapping_deserialized = kajson.loads(wrapping_serialized)  # pyright: ignore[reportUnknownMemberType]
        assert isinstance(wrapping_deserialized, PipeSequenceBlueprint)
        assert len(wrapping_deserialized.steps) == 2

        structure_serialized = kajson.dumps(elaborated.pipe["make_foo__structure"])  # pyright: ignore[reportUnknownMemberType]
        structure_deserialized = kajson.loads(structure_serialized)  # pyright: ignore[reportUnknownMemberType]
        assert isinstance(structure_deserialized, PipeStructureBlueprint)
        assert structure_deserialized.inputs == {"draft_text": "Text"}
        assert structure_deserialized.output == "Foo"
