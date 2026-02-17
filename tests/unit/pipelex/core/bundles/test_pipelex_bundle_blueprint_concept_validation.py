import pytest
from pydantic import ValidationError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class TestPipelexBundleBlueprintConceptValidation:
    """Test validation of local concept references in PipelexBundleBlueprint."""

    # ========== VALID CASES ==========

    def test_valid_native_concept_in_pipe_output(self):
        """Native concepts like Text should be valid without declaration."""
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
        """Native concepts in inputs should be valid without declaration."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"data": "Text", "image": "Image"},
                    output="Text",
                    prompt="Process @data and @image",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_declared_local_concept_in_pipe_output(self):
        """Local concept that is declared in the bundle should be valid."""
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
        """Local concept in inputs that is declared should be valid."""
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
                    prompt="Process @data",
                ),
            },
        )
        assert bundle.concept is not None

    def test_valid_same_domain_concept_ref_declared(self):
        """Same-domain concept ref (domain.Concept) that is declared should be valid."""
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

    def test_valid_external_domain_concept_ref_not_validated(self):
        """External domain concept ref should not be validated (assumed to be from dependency)."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"external_data": "other_domain.ExternalConcept"},
                    output="Text",
                    prompt="Process @external_data",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_native_concept_with_domain_prefix(self):
        """Native concepts with native. prefix should be valid."""
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
        """Concepts with multiplicity brackets should be validated correctly."""
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
                    prompt="Process @items",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_valid_declared_concept_in_refines(self):
        """Concept declared in the bundle can be referenced in refines field."""
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
        """Native concepts can be referenced in refines without declaration."""
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
        """Concept refs in structure fields should be validated."""
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
        """Item concept refs in list fields should be validated."""
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

    # ========== HIERARCHICAL DOMAIN CASES ==========

    def test_valid_hierarchical_domain_concept_ref_output(self):
        """Hierarchical domain concept ref for same domain should be valid."""
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
        """External concept ref from a different hierarchical domain should be skipped."""
        bundle = PipelexBundleBlueprint(
            domain="legal.contracts",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    type="PipeLLM",
                    description="Test pipe",
                    inputs={"score": "scoring.WeightedScore"},
                    output="Text",
                    prompt="Process @score",
                ),
            },
        )
        assert bundle.pipe is not None

    def test_invalid_hierarchical_domain_undeclared_same_domain(self):
        """Hierarchical same-domain concept ref that is not declared should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="legal.contracts",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        output="legal.contracts.Missing",
                        prompt="Generate something",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "Missing" in error_message
        assert "not declared in domain" in error_message

    # ========== INVALID CASES ==========

    def test_invalid_undeclared_local_concept_in_pipe_output(self):
        """Undeclared local concept in pipe output should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        output="UndeclaredConcept",
                        prompt="Generate something",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "UndeclaredConcept" in error_message
        assert "pipe.my_pipe.output" in error_message
        assert "not declared in domain" in error_message

    def test_invalid_undeclared_local_concept_in_pipe_input(self):
        """Undeclared local concept in pipe input should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        inputs={"data": "UndeclaredInput"},
                        output="Text",
                        prompt="Process @data",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "UndeclaredInput" in error_message
        assert "pipe.my_pipe.inputs.data" in error_message

    def test_invalid_undeclared_same_domain_concept_ref(self):
        """Same-domain concept ref that is not declared should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        output="my_domain.NotDeclaredConcept",
                        prompt="Generate something",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "NotDeclaredConcept" in error_message
        assert "pipe.my_pipe.output" in error_message

    def test_invalid_undeclared_concept_in_refines(self):
        """Undeclared concept in refines field should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                concept={
                    "DerivedConcept": ConceptBlueprint(
                        description="Derived concept",
                        refines="NonExistentBaseConcept",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "NonExistentBaseConcept" in error_message
        assert "concept.DerivedConcept.refines" in error_message

    def test_invalid_undeclared_concept_ref_in_structure(self):
        """Undeclared concept ref in structure field should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                concept={
                    "Person": ConceptBlueprint(
                        description="A person concept",
                        structure={
                            "name": "The person's name",
                            "address": ConceptStructureBlueprint(
                                description="The person's address",
                                type=ConceptStructureBlueprintFieldType.CONCEPT,
                                concept_ref="UndeclaredAddress",
                            ),
                        },
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "UndeclaredAddress" in error_message
        assert "concept.Person.structure.address.concept_ref" in error_message

    def test_invalid_undeclared_item_concept_ref_in_structure(self):
        """Undeclared item concept ref in list field should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="my_domain",
                description="Test bundle",
                concept={
                    "Order": ConceptBlueprint(
                        description="An order concept",
                        structure={
                            "order_id": "The order ID",
                            "items": ConceptStructureBlueprint(
                                description="The order items",
                                type=ConceptStructureBlueprintFieldType.LIST,
                                item_type="concept",
                                item_concept_ref="UndeclaredLineItem",
                            ),
                        },
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "UndeclaredLineItem" in error_message
        assert "concept.Order.structure.items.item_concept_ref" in error_message

    def test_invalid_undeclared_concept_with_multiplicity(self):
        """Undeclared concept with multiplicity brackets should raise error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        inputs={"items": "UndeclaredItem[]"},
                        output="Text",
                        prompt="Process @items",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "UndeclaredItem" in error_message
        assert "pipe.my_pipe.inputs.items" in error_message

    def test_invalid_multiple_undeclared_concepts(self):
        """Multiple undeclared concepts should all be reported in error."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        inputs={"input1": "Undeclared1", "input2": "Undeclared2"},
                        output="Undeclared3",
                        prompt="Process @input1 and @input2",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "Undeclared1" in error_message
        assert "Undeclared2" in error_message
        assert "Undeclared3" in error_message

    def test_error_message_includes_declared_concepts(self):
        """Error message should include list of declared concepts for debugging."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                concept={
                    "DeclaredConcept1": "First declared concept",
                    "DeclaredConcept2": "Second declared concept",
                },
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        output="UndeclaredConcept",
                        prompt="Generate",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "DeclaredConcept1" in error_message
        assert "DeclaredConcept2" in error_message

    def test_error_message_includes_native_concepts(self):
        """Error message should mention native concepts."""
        with pytest.raises(ValidationError) as exc_info:
            PipelexBundleBlueprint(
                domain="test_domain",
                description="Test bundle",
                pipe={
                    "my_pipe": PipeLLMBlueprint(
                        type="PipeLLM",
                        description="Test pipe",
                        output="UndeclaredConcept",
                        prompt="Generate",
                    ),
                },
            )

        error_message = str(exc_info.value)
        assert "Native concepts" in error_message
        assert "Text" in error_message
