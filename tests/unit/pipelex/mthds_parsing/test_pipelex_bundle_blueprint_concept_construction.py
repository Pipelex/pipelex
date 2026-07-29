from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipelexBundleBlueprintConceptConstruction:
    """Construction smoke tests for concept references in PipelexBundleBlueprint.

    A bundle no longer validates same-domain concept references per file: a concept declared in a
    sibling file may be referenced here, so construction always succeeds regardless of declaration.
    Reference resolution against the merged library now lives in
    tests/unit/pipelex/libraries/test_library_crate_concept_references.py. These tests pin that the
    various concept-reference shapes still parse and construct.
    """

    def test_valid_native_concept_in_pipe_output(self):
        """Native concepts like Text construct without declaration."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    output="Text",
                    prompt="Hello",
                ),
            },
        )
        assert bundle.pipe is not None
        assert "my_pipe" in bundle.pipe

    def test_valid_native_concept_in_pipe_input(self):
        """Native concepts in inputs construct without declaration."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"data": "Text", "image": "Image"},
                    output="Text",
                    prompt="Process $data and $image",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_declared_local_concept_in_pipe_output(self):
        """A local concept declared in the bundle and used in a pipe output constructs."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            concept={"MyCustomConcept": "A custom concept"},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    output="MyCustomConcept",
                    prompt="Generate something",
                ),
            },
        )
        assert bundle.concept is not None
        assert "MyCustomConcept" in bundle.concept

    def test_valid_declared_local_concept_in_pipe_input(self):
        """A local concept declared in the bundle and used in a pipe input constructs."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            concept={"InputData": "Input data concept"},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"data": "InputData"},
                    output="Text",
                    prompt="Process $data",
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_same_domain_concept_ref_declared(self):
        """A same-domain concept ref (domain.Concept) constructs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={"MyCustomConcept": "A custom concept"},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    output="my_domain.MyCustomConcept",
                    prompt="Generate something",
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_external_domain_concept_ref(self):
        """An external-domain concept ref constructs (resolved later via dependencies)."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"external_data": "other_domain.ExternalConcept"},
                    output="Text",
                    prompt="Process $external_data",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_native_concept_with_domain_prefix(self):
        """Native concepts with the native. prefix construct."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    output="native.Text",
                    prompt="Hello",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_concept_with_multiplicity(self):
        """Concepts with multiplicity brackets construct."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            concept={"Item": "An item concept"},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"items": "Item[]"},
                    output="Text[3]",
                    prompt="Process $items",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_declared_concept_in_refines(self):
        """A concept refining another concept declared in the bundle constructs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={
                "BaseConcept": "Base concept",
                "DerivedConcept": ConceptBlueprint(
                    description="Derived concept",
                    refines="BaseConcept",
                ),
            },
        )
        assert bundle.concept is not None
        assert "DerivedConcept" in bundle.concept

    def test_valid_native_concept_in_refines(self):
        """A concept refining a native concept constructs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={
                "MyTextConcept": ConceptBlueprint(
                    description="A text-based concept",
                    refines="Text",
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_concept_ref_in_structure(self):
        """A concept ref in a structure field constructs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={
                "Address": "An address concept",
                "Person": ConceptBlueprint(
                    description="A person concept",
                    structure={
                        "name": "The person's name",
                        "address": ConceptStructureBlueprint(
                            description="The person's address",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="Address",
                        ),
                    },
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_item_concept_ref_in_structure(self):
        """An item concept ref in a list structure field constructs."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={
                "LineItem": "A line item concept",
                "Order": ConceptBlueprint(
                    description="An order concept",
                    structure={
                        "order_id": "The order ID",
                        "items": ConceptStructureBlueprint(
                            description="The order items",
                            type=ConceptStructureBlueprintFieldType.LIST,
                            item_type="concept",
                            item_concept_ref="LineItem",
                        ),
                    },
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_hierarchical_domain_concept_ref_output(self):
        """A hierarchical same-domain concept ref in a pipe output constructs."""
        bundle = PipelexBundleBlueprint(
            domain="legal.contracts",
            description="Test bundle",
            concept={"NonCompeteClause": "A non-compete clause concept"},
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    output="legal.contracts.NonCompeteClause",
                    prompt="Generate something",
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_hierarchical_domain_external_concept_ref(self):
        """An external concept ref from a different hierarchical domain constructs."""
        bundle = PipelexBundleBlueprint(
            domain="legal.contracts",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"score": "scoring.WeightedScore"},
                    output="Text",
                    prompt="Process $score",
                ),
            },
        )
        assert bundle.pipe is not None
