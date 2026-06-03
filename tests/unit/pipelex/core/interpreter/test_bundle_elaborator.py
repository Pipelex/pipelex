import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint, StepRole
from pipelex.core.interpreter.bundle_elaborator import BundleElaborator
from pipelex.core.interpreter.exceptions import BundleElaboratorError
from pipelex.pipe_controllers.sequence.pipe_sequence_blueprint import PipeSequenceBlueprint
from pipelex.pipe_operators.func.pipe_func_blueprint import PipeFuncBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint, StructuringMethod
from pipelex.pipe_operators.structure.pipe_structure_blueprint import PipeStructureBlueprint


class TestBundleElaborator:
    def test_short_circuits_when_no_preliminary_text(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="No preliminary_text here",
            concept={"Foo": "A foo"},
            pipe={
                "plain_llm": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Plain",
                    output="Foo",
                    prompt="hello",
                ),
                "plain_func": PipeFuncBlueprint(
                    type="PipeFunc",
                    description="Plain",
                    output="Foo",
                    function_name="my_func",
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        # Identity check: short-circuit must return the same instance.
        assert elaborated is bundle

    def test_empty_pipe_dict_short_circuits(self):
        bundle = PipelexBundleBlueprint(domain="my_domain", description="Empty", pipe={})
        assert BundleElaborator.elaborate(bundle=bundle) is bundle

        bundle_none = PipelexBundleBlueprint(domain="my_domain", description="Empty")
        assert BundleElaborator.elaborate(bundle=bundle_none) is bundle_none

    def test_elaborates_preliminary_text_to_three_pipes(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="With preliminary_text",
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
        assert elaborated is not bundle  # new bundle was built
        assert elaborated.pipe is not None
        assert set(elaborated.pipe.keys()) == {"make_foo", "make_foo__draft_text", "make_foo__structure"}

        wrapping = elaborated.pipe["make_foo"]
        assert isinstance(wrapping, PipeSequenceBlueprint)
        assert len(wrapping.steps) == 2
        assert wrapping.steps[0].pipe == "make_foo__draft_text"
        assert wrapping.steps[0].result == "draft_text"
        assert wrapping.steps[1].pipe == "make_foo__structure"
        assert wrapping.output == "Foo"

        draft = elaborated.pipe["make_foo__draft_text"]
        assert isinstance(draft, PipeLLMBlueprint)
        assert draft.output == "Text"
        assert draft.structuring_method is None
        assert draft.prompt == "Talk about $topic"

        structure = elaborated.pipe["make_foo__structure"]
        assert isinstance(structure, PipeStructureBlueprint)
        assert structure.inputs == {"draft_text": "Text"}
        assert structure.output == "Foo"

        # Side-table populated
        assert elaborated.elaboration_metadata is not None
        assert "make_foo__draft_text" in elaborated.elaboration_metadata
        assert "make_foo__structure" in elaborated.elaboration_metadata
        assert elaborated.elaboration_metadata["make_foo__draft_text"].step_role is StepRole.DRAFT_TEXT
        assert elaborated.elaboration_metadata["make_foo__structure"].step_role is StepRole.STRUCTURE
        # Wrapping sequence is NOT in metadata — it's the user-facing pipe.
        assert "make_foo" not in elaborated.elaboration_metadata

    @pytest.mark.parametrize(("output_str", "expected_step1_output"), [("Foo", "Text"), ("Foo[]", "Text"), ("Foo[3]", "Text")])
    def test_step1_output_is_always_single_text(self, output_str: str, expected_step1_output: str):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test multiplicity preservation",
            concept={"Foo": "A foo"},
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Make a Foo",
                    output=output_str,
                    prompt="hello",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        draft = elaborated.pipe["make_foo__draft_text"]
        assert isinstance(draft, PipeLLMBlueprint)
        assert draft.output == expected_step1_output

        structure = elaborated.pipe["make_foo__structure"]
        assert isinstance(structure, PipeStructureBlueprint)
        assert structure.output == output_str

    @pytest.mark.parametrize("bad_output", ["Text", "Text[]", "Text[2]", "native.Text"])
    def test_text_output_rejected_at_blueprint_construction(self, bad_output: str):
        # The user-facing gate: PipeLLMBlueprint's model_validator catches the bad combo
        # before the elaborator ever runs, so users see the error during MTHDS parsing.
        with pytest.raises(ValueError, match="cannot have output"):
            PipeLLMBlueprint(
                type="PipeLLM",
                description="Bad",
                output=bad_output,
                prompt="hello",
                structuring_method=StructuringMethod.PRELIMINARY_TEXT,
            )

    def test_text_output_caught_by_elaborator_defense_in_depth(self):
        # If a programmatic caller bypasses Pydantic validation (e.g. via model_construct),
        # the elaborator's own pre-check still raises with a message naming the user's pipe code.
        bad_blueprint = PipeLLMBlueprint.model_construct(
            type="PipeLLM",
            pipe_category="PipeOperator",
            description="Bad",
            inputs=None,
            output="Text",
            prompt="hello",
            structuring_method=StructuringMethod.PRELIMINARY_TEXT,
        )
        bundle = PipelexBundleBlueprint.model_construct(
            domain="my_domain",
            description="Bad",
            concept={},
            pipe={"make_text": bad_blueprint},
        )
        with pytest.raises(BundleElaboratorError, match="make_text"):
            BundleElaborator.elaborate(bundle=bundle)

    def test_synthetic_name_collision_raises(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Collision",
            concept={"Foo": "A foo"},
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Original",
                    output="Foo",
                    prompt="hello",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
                "make_foo__draft_text": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Pre-existing collision",
                    output="Text",
                    prompt="hi",
                ),
            },
        )
        with pytest.raises(BundleElaboratorError, match="collide"):
            BundleElaborator.elaborate(bundle=bundle)

    def test_image_input_only_on_step_1(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Image input flows to step-1 only",
            concept={"Foo": "A foo"},
            pipe={
                "describe_image": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Describe an image",
                    inputs={"page_image": "Image"},
                    output="Foo",
                    prompt="Describe $page_image",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        draft = elaborated.pipe["describe_image__draft_text"]
        structure = elaborated.pipe["describe_image__structure"]
        assert isinstance(draft, PipeLLMBlueprint)
        assert isinstance(structure, PipeStructureBlueprint)
        assert draft.inputs == {"page_image": "Image"}
        assert structure.inputs == {"draft_text": "Text"}

    def test_main_pipe_still_resolves_after_elaboration(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="main_pipe regression",
            concept={"Foo": "A foo"},
            main_pipe="make_foo",
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Main",
                    output="Foo",
                    prompt="hello",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        assert elaborated.main_pipe == "make_foo"
        assert "make_foo" in elaborated.pipe
        # The wrapping sequence is a PipeSequenceBlueprint
        assert isinstance(elaborated.pipe["make_foo"], PipeSequenceBlueprint)

    def test_model_to_structure_propagates_to_step_2(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Model propagation",
            concept={"Foo": "A foo"},
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Make a Foo",
                    output="Foo",
                    prompt="hello",
                    model="some-text-model",
                    model_to_structure="some-structure-model",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        structure = elaborated.pipe["make_foo__structure"]
        draft = elaborated.pipe["make_foo__draft_text"]
        assert isinstance(structure, PipeStructureBlueprint)
        assert isinstance(draft, PipeLLMBlueprint)
        assert structure.model is not None  # parsed to ModelReference
        assert draft.model is not None
        assert draft.model_to_structure is None

    def test_model_to_structure_none_yields_step_2_default(self):
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Default propagation",
            concept={"Foo": "A foo"},
            pipe={
                "make_foo": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Make a Foo",
                    output="Foo",
                    prompt="hello",
                    structuring_method=StructuringMethod.PRELIMINARY_TEXT,
                ),
            },
        )
        elaborated = BundleElaborator.elaborate(bundle=bundle)
        assert elaborated.pipe is not None
        structure = elaborated.pipe["make_foo__structure"]
        assert isinstance(structure, PipeStructureBlueprint)
        assert structure.model is None
