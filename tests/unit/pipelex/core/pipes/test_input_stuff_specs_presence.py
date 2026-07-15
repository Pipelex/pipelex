from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker


def _text_concept() -> Concept:
    return ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)


class TestInputStuffSpecsPresence:
    """The required vs declared split: declared_names lists every input, required_names excludes optional ones."""

    def _make_specs(self) -> InputStuffSpecs:
        concept = _text_concept()
        return InputStuffSpecs(
            root={
                "plain_var": StuffSpec(concept=concept),
                "optional_var": StuffSpec(concept=concept, presence=PresenceMarker.OPTIONAL),
                "forced_var": StuffSpec(concept=concept, presence=PresenceMarker.FORCE),
            },
        )

    def test_declared_names_lists_all_inputs(self):
        specs = self._make_specs()
        assert specs.declared_names == ["plain_var", "optional_var", "forced_var"]

    def test_required_names_excludes_optional_inputs(self):
        specs = self._make_specs()
        assert specs.required_names == ["plain_var", "forced_var"]

    def test_required_equals_declared_without_markers(self):
        concept = _text_concept()
        specs = InputStuffSpecs(root={"var_a": StuffSpec(concept=concept), "var_b": StuffSpec(concept=concept, multiplicity=True)})
        assert specs.required_names == specs.declared_names == ["var_a", "var_b"]

    def test_named_stuff_specs_carry_presence(self):
        specs = self._make_specs()
        presence_by_name = {named.variable_name: named.presence for named in specs.named_stuff_specs}
        assert presence_by_name == {
            "plain_var": PresenceMarker.PLAIN,
            "optional_var": PresenceMarker.OPTIONAL,
            "forced_var": PresenceMarker.FORCE,
        }

    def test_add_stuff_spec_carries_presence(self):
        specs = InputStuffSpecs(root={})
        specs.add_stuff_spec(variable_name="maybe_var", concept=_text_concept(), presence=PresenceMarker.OPTIONAL)
        assert specs.root["maybe_var"].presence == PresenceMarker.OPTIONAL

    def test_root_validator_preserves_presence(self):
        """The wrap validator rebuilds StuffSpecs (dotted-path rooting) and must not drop presence."""
        concept = _text_concept()
        specs = InputStuffSpecs(root={"doc.summary": StuffSpec(concept=concept, presence=PresenceMarker.OPTIONAL)})
        assert specs.root["doc"].presence == PresenceMarker.OPTIONAL
