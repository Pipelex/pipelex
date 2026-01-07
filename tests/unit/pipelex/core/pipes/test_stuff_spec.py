import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.core.pipes.variable_multiplicity import VariableMultiplicity


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
