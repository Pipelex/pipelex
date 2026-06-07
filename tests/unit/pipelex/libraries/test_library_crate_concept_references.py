import pytest

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.libraries.concept.exceptions import ConceptLibraryError
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from tests.unit.pipelex.libraries.test_library_crate_data import BlueprintSamples


class TestLibraryCrateConceptReferences:
    """Concept references resolve against the merged library, not per file.

    These cases moved here from the per-file blueprint validator: a bundle now constructs even
    when it references a concept declared in a sibling file, and an undeclared reference is caught
    at merge time by LibraryCrateFactory.make_from_blueprints.
    """

    # ========== CROSS-FILE RESOLUTION (the unblock) ==========

    @pytest.mark.parametrize(
        "blueprints",
        [
            [BlueprintSamples.CROSSREF_CONCEPT_BUNDLE, BlueprintSamples.CROSSREF_PIPE_BUNDLE],
            [BlueprintSamples.CROSSREF_PIPE_BUNDLE, BlueprintSamples.CROSSREF_CONCEPT_BUNDLE],
        ],
    )
    def test_cross_file_concept_reference_resolves(self, blueprints: list[PipelexBundleBlueprint]):
        """A concept declared in one file, referenced by bare code from a sibling file, resolves (order-independent)."""
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=blueprints)
        assert "crossref.Summary" in crate.concepts
        assert "crossref.make_summary" in crate.pipes

    def test_cross_file_undeclared_concept_raises_naming_ref_and_source(self):
        """A bare concept reference declared in no file raises ConceptLibraryError naming the ref and its source."""
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[BlueprintSamples.CROSSREF_PIPE_BUNDLE])
        message = str(exc_info.value)
        assert "Summary" in message
        assert "pipe.make_summary.output" in message
        assert "/fake/crossref_pipe.mthds" in message

    # ========== REFERENCES DEFERRED TO OTHER LAYERS (no error) ==========

    def test_native_concept_reference_allowed(self):
        """Native concepts (Text) need no declaration and never trigger the undeclared check."""
        bundle = PipelexBundleBlueprint(
            domain="native_ok",
            description="Native concepts only",
            pipe={
                "echo": PipeLLMBlueprint(
                    description="Echo a document",
                    inputs={"doc": "Text"},
                    output="Text",
                    prompt="Echo $doc.",
                ),
            },
        )
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        assert "native_ok.echo" in crate.pipes

    def test_external_domain_reference_not_validated(self):
        """An external-domain concept ref is deferred to dependency loading, not flagged here."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="External ref",
            pipe={
                "use_external": PipeLLMBlueprint(
                    description="Use an external concept",
                    inputs={"score": "scoring.WeightedScore"},
                    output="Text",
                    prompt="Process $score.",
                ),
            },
        )
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        assert "my_domain.use_external" in crate.pipes

    def test_cross_package_reference_not_validated(self):
        """A cross-package concept ref ('alias->...') is deferred to package resolution, not flagged here."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Cross-package ref",
            concept={
                "Wrapper": ConceptBlueprint(
                    description="Wraps a dependency concept",
                    structure={
                        "doc": ConceptStructureBlueprint(
                            description="A document from a dependency package",
                            type=ConceptStructureBlueprintFieldType.CONCEPT,
                            concept_ref="docs->documents.Document",
                        ),
                    },
                ),
            },
        )
        crate = LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        assert "my_domain.Wrapper" in crate.concepts

    # ========== RELOCATED UNDECLARED-REFERENCE CASES (now caught at merge) ==========

    def test_undeclared_concept_in_pipe_output_raises(self):
        """An undeclared concept in a pipe output is caught at merge with its context path."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    output="UndeclaredConcept",
                    prompt="Generate something",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "UndeclaredConcept" in message
        assert "pipe.my_pipe.output" in message
        assert "not declared in domain" in message

    def test_undeclared_concept_in_pipe_input_raises(self):
        """An undeclared concept in a pipe input is caught at merge with its context path."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    inputs={"data": "UndeclaredInput"},
                    output="Text",
                    prompt="Process $data",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "UndeclaredInput" in message
        assert "pipe.my_pipe.inputs.data" in message

    def test_undeclared_same_domain_qualified_reference_raises(self):
        """A same-domain qualified ref (domain.Concept) not declared anywhere is caught at merge."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    output="my_domain.NotDeclaredConcept",
                    prompt="Generate something",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "NotDeclaredConcept" in message
        assert "pipe.my_pipe.output" in message

    def test_undeclared_hierarchical_same_domain_reference_raises(self):
        """A hierarchical same-domain qualified ref not declared anywhere is caught at merge."""
        bundle = PipelexBundleBlueprint(
            domain="legal.contracts",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    output="legal.contracts.Missing",
                    prompt="Generate something",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "Missing" in message
        assert "not declared in domain" in message

    def test_undeclared_concept_in_refines_raises(self):
        """An undeclared concept in a refines field is caught at merge with its context path."""
        bundle = PipelexBundleBlueprint(
            domain="my_domain",
            description="Test bundle",
            concept={
                "DerivedConcept": ConceptBlueprint(
                    description="Derived concept",
                    refines="NonExistentBaseConcept",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "NonExistentBaseConcept" in message
        assert "concept.DerivedConcept.refines" in message

    def test_undeclared_concept_ref_in_structure_raises(self):
        """An undeclared concept_ref in a structure field is caught at merge with its context path."""
        bundle = PipelexBundleBlueprint(
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
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "UndeclaredAddress" in message
        assert "concept.Person.structure.address.concept_ref" in message

    def test_undeclared_item_concept_ref_in_structure_raises(self):
        """An undeclared item_concept_ref in a list structure field is caught at merge."""
        bundle = PipelexBundleBlueprint(
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
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "UndeclaredLineItem" in message
        assert "concept.Order.structure.items.item_concept_ref" in message

    def test_undeclared_concept_with_multiplicity_raises(self):
        """A multiplicity-bracketed undeclared concept resolves to its base code and is caught at merge."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    inputs={"items": "UndeclaredItem[]"},
                    output="Text",
                    prompt="Process $items",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "UndeclaredItem" in message
        assert "pipe.my_pipe.inputs.items" in message

    def test_multiple_undeclared_concepts_all_reported(self):
        """Every undeclared reference is reported together, not just the first."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    inputs={"input1": "Undeclared1", "input2": "Undeclared2"},
                    output="Undeclared3",
                    prompt="Process $input1 and $input2",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "Undeclared1" in message
        assert "Undeclared2" in message
        assert "Undeclared3" in message

    def test_error_message_lists_declared_and_native_concepts(self):
        """The error message lists the declared concepts and native concepts for debugging."""
        bundle = PipelexBundleBlueprint(
            domain="test_domain",
            description="Test bundle",
            concept={
                "DeclaredConcept1": "First declared concept",
                "DeclaredConcept2": "Second declared concept",
            },
            pipe={
                "my_pipe": PipeLLMBlueprint(
                    description="Test pipe",
                    output="UndeclaredConcept",
                    prompt="Generate",
                ),
            },
        )
        with pytest.raises(ConceptLibraryError) as exc_info:
            LibraryCrateFactory.make_from_blueprints(blueprints=[bundle])
        message = str(exc_info.value)
        assert "DeclaredConcept1" in message
        assert "DeclaredConcept2" in message
        assert "Native concepts" in message
        assert "Text" in message
