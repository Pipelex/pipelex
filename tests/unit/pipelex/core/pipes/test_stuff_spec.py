import pytest
from typing_extensions import override

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.concepts.concept_representation_generator import ConceptRepresentationFormat
from pipelex.core.concepts.exceptions import ConceptValueError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import PresenceMarker, VariableMultiplicity
from pipelex.core.stuffs.stuff_content import StuffContent


class TestStuffSpecToBundleRepresentation:
    """Test the StuffSpec.to_bundle_representation method."""

    @pytest.mark.parametrize(
        ("multiplicity", "expected_suffix"),
        [
            # No multiplicity - returns just concept_ref
            (None, ""),
            # Boolean multiplicity (variable-length list)
            (True, "[]"),
            # Integer multiplicity (fixed-length list)
            (1, "[1]"),
            (3, "[3]"),
            (10, "[10]"),
            (999, "[999]"),
        ],
    )
    def test_to_bundle_representation_with_native_text(
        self,
        multiplicity: VariableMultiplicity | None,
        expected_suffix: str,
    ):
        """Test to_bundle_representation with native.Text concept and various multiplicities."""
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        stuff_spec = StuffSpec(concept=concept, multiplicity=multiplicity)

        result = stuff_spec.to_bundle_representation()

        expected = f"{concept.concept_ref}{expected_suffix}"
        assert result == expected
        assert result == f"native.Text{expected_suffix}"

    @pytest.mark.parametrize(
        ("native_concept_code", "multiplicity", "expected"),
        [
            # Various native concepts without multiplicity
            (NativeConceptCode.TEXT, None, "native.Text"),
            (NativeConceptCode.IMAGE, None, "native.Image"),
            (NativeConceptCode.DOCUMENT, None, "native.Document"),
            (NativeConceptCode.NUMBER, None, "native.Number"),
            # Various native concepts with variable-length list
            (NativeConceptCode.TEXT, True, "native.Text[]"),
            (NativeConceptCode.IMAGE, True, "native.Image[]"),
            # Various native concepts with fixed-length list
            (NativeConceptCode.TEXT, 5, "native.Text[5]"),
            (NativeConceptCode.IMAGE, 3, "native.Image[3]"),
        ],
    )
    def test_to_bundle_representation_with_various_native_concepts(
        self,
        native_concept_code: NativeConceptCode,
        multiplicity: VariableMultiplicity | None,
        expected: str,
    ):
        """Test to_bundle_representation with different native concept types."""
        concept = ConceptFactory.make_native_concept(native_concept_code=native_concept_code)
        stuff_spec = StuffSpec(concept=concept, multiplicity=multiplicity)

        result = stuff_spec.to_bundle_representation()

        assert result == expected

    def test_to_bundle_representation_with_custom_domain_concept(self):
        """Test to_bundle_representation with a custom domain concept."""
        concept = ConceptFactory.make(
            domain_code="my_domain",
            concept_code="MyCustomConcept",
            description="A custom concept for testing",
            structure_class_name="TextContent",
        )
        stuff_spec_single = StuffSpec(concept=concept, multiplicity=None)
        stuff_spec_list = StuffSpec(concept=concept, multiplicity=True)
        stuff_spec_fixed = StuffSpec(concept=concept, multiplicity=7)

        assert stuff_spec_single.to_bundle_representation() == "my_domain.MyCustomConcept"
        assert stuff_spec_list.to_bundle_representation() == "my_domain.MyCustomConcept[]"
        assert stuff_spec_fixed.to_bundle_representation() == "my_domain.MyCustomConcept[7]"

    def test_presence_defaults_to_plain(self):
        """A StuffSpec built without presence is plain (required, always produced)."""
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        stuff_spec = StuffSpec(concept=concept)
        assert stuff_spec.presence == PresenceMarker.PLAIN

    @pytest.mark.parametrize(
        ("presence", "expected"),
        [
            (PresenceMarker.PLAIN, "native.Text"),
            (PresenceMarker.OPTIONAL, "native.Text?"),
            (PresenceMarker.FORCE, "native.Text!"),
        ],
    )
    def test_to_bundle_representation_with_presence(self, presence: PresenceMarker, expected: str):
        """to_bundle_representation renders the presence marker suffix."""
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        stuff_spec = StuffSpec(concept=concept, presence=presence)
        assert stuff_spec.to_bundle_representation() == expected


class _RefusingConceptProvider(ConceptProviderAbstract):
    """A provider whose class resolution must never be reached — structureless renders resolve nothing."""

    @override
    def get_required_concept(self, concept_ref: str) -> Concept:
        msg = "get_required_concept must not be called for a structureless render"
        raise AssertionError(msg)

    @override
    def get_native_concept(self, native_concept: NativeConceptCode) -> Concept:
        msg = "get_native_concept must not be called for a structureless render"
        raise AssertionError(msg)

    @override
    def get_required_entry_concept(self, concept_ref_or_code: str, *, search_scope: str | None = None) -> Concept:
        msg = "get_required_entry_concept must not be called for a structureless render"
        raise AssertionError(msg)

    @override
    def is_compatible(self, *, tested_concept: Concept, wanted_concept: Concept, strict: bool = False) -> bool:
        msg = "is_compatible must not be called for a structureless render"
        raise AssertionError(msg)

    @override
    def get_structure_class(self, *, concept: Concept) -> type[StuffContent]:
        msg = "get_structure_class must not be called for a structureless render"
        raise AssertionError(msg)


class TestStuffSpecStructurelessRender:
    """`native.Anything` renders without resolving a structure class.

    SCHEMA publishes the permissive schema — no constraint keywords, only the concept's identity
    annotations (`title` = concept ref, `description` = authored description); JSON renders the
    empty mapping. Multiplicity wraps exactly as for class-backed concepts.
    """

    def test_schema_single_is_annotated_permissive(self):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept)

        result = stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.SCHEMA)

        assert result["concept"] == "native.Anything"
        assert result["content"] == {"title": "native.Anything", "description": concept.description}

    def test_schema_variable_list_wraps_in_unbounded_array(self):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept, multiplicity=True)

        result = stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.SCHEMA)

        assert result["content"] == {
            "type": "array",
            "items": {"title": "native.Anything", "description": concept.description},
        }

    def test_schema_fixed_count_bounds_the_array(self):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept, multiplicity=3)

        result = stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.SCHEMA)

        assert result["content"] == {
            "type": "array",
            "items": {"title": "native.Anything", "description": concept.description},
            "minItems": 3,
            "maxItems": 3,
        }

    def test_json_single_is_empty_mapping(self):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept)

        result = stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.JSON)

        assert result == {"concept": "native.Anything", "content": {}}

    @pytest.mark.parametrize("multiplicity", [True, 3])
    def test_json_multiple_wraps_in_list(self, multiplicity: VariableMultiplicity):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept, multiplicity=multiplicity)

        result = stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.JSON)

        assert result == {"concept": "native.Anything", "content": [{}]}

    def test_python_format_is_refused(self):
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.ANYTHING)
        stuff_spec = StuffSpec(concept=concept)

        with pytest.raises(ConceptValueError, match="no structure class"):
            stuff_spec.render_stuff_spec(concept_provider=_RefusingConceptProvider(), output_format=ConceptRepresentationFormat.PYTHON)
