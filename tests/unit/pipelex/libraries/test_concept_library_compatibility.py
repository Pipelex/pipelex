"""`ConceptLibrary` composes the two compatibility tiers, and fails loudly when it cannot.

`is_compatible` asks the declaration tier first; only when that is inconclusive does it resolve both
structure classes and compare them. An unresolvable structure class is *not* an answer to the
compatibility question — it means the library was asked about a concept whose class it does not
hold — so it raises `ConceptStructureClassNotFoundError` rather than returning `False`, which would
be indistinguishable from a genuine "incompatible" verdict.
"""

from __future__ import annotations

import pytest
from kajson.kajson_manager import KajsonManager
from pydantic import Field

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.concept_structure_blueprint import ConceptStructureBlueprint, ConceptStructureBlueprintFieldType
from pipelex.core.concepts.exceptions import ConceptStructureClassNotFoundError, ConceptValueError
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.libraries.concept.concept_library import ConceptLibrary


class UnrelatedRedContent(StructuredContent):
    red: str


class UnrelatedBlueContent(StructuredContent):
    blue: int


class NestedImageInfo(StructuredContent):
    """A nested structure that contains image-like data (same structure as ImageContent)."""

    url: str
    public_url: str | None = None
    source_prompt: str | None = None
    source_negative_prompt: str | None = None
    caption: str | None = None
    mime_type: str | None = None
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    filename: str | None = None


class DocumentWithNestedImage(StructuredContent):
    """A content class that has a nested field containing image info."""

    title: str
    metadata: NestedImageInfo


def _make_concept(*, code: str, domain_code: str, structure_class_name: str, refines: str | None = None) -> Concept:
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name=structure_class_name,
        refines=refines,
    )


class TestConceptLibraryCompatibility:
    def test_unregistered_structure_class_raises_instead_of_answering_false(self):
        """Declaration tier inconclusive + classes absent from the registry => loud, not `False`."""
        library = ConceptLibrary.make_empty()
        one = _make_concept(code="Ghost", domain_code="nowhere", structure_class_name="GhostContentThatIsNeverRegistered")
        other = _make_concept(code="Phantom", domain_code="elsewhere", structure_class_name="PhantomContentThatIsNeverRegistered")

        with pytest.raises(ConceptStructureClassNotFoundError):
            library.is_compatible(tested_concept=one, wanted_concept=other)

    def test_the_new_error_is_catchable_as_the_existing_concept_value_error(self):
        """Guards that already catch `ConceptValueError` keep working unmodified."""
        assert issubclass(ConceptStructureClassNotFoundError, ConceptValueError)

    def test_declaration_tier_short_circuits_before_any_class_lookup(self):
        """A declaration-established pair never touches the registry, so unregistered classes are fine."""
        library = ConceptLibrary.make_empty()
        base = _make_concept(code="BaseScore", domain_code="scoring", structure_class_name="NeverRegisteredBaseContent")
        refining = _make_concept(
            code="DetailedScore",
            domain_code="scoring",
            structure_class_name="NeverRegisteredDetailedContent",
            refines="scoring.BaseScore",
        )

        assert library.is_compatible(tested_concept=refining, wanted_concept=base) is True

    def test_registered_but_unrelated_classes_answer_false(self):
        """The class tier still answers `False` — an unregistered class is a different situation."""
        KajsonManager.get_class_registry().register_class(UnrelatedRedContent)
        KajsonManager.get_class_registry().register_class(UnrelatedBlueContent)

        library = ConceptLibrary.make_empty()
        one = _make_concept(code="Red", domain_code="palette", structure_class_name="UnrelatedRedContent")
        other = _make_concept(code="Blue", domain_code="palette", structure_class_name="UnrelatedBlueContent")

        assert library.is_compatible(tested_concept=one, wanted_concept=other) is False

    def test_the_structureless_native_concept_is_answered_not_raised(self):
        """`native.Anything` declares no content class, so there is no structural check to attempt.

        This is the one case where "no class" is a property of the concept rather than a missing
        registration, and it must stay a plain `False` — the loud raise is for names that *should*
        have resolved.
        """
        library = ConceptLibrary.make_empty_with_native_concepts()
        anything = library.get_native_concept(native_concept=NativeConceptCode.ANYTHING)
        text = library.get_native_concept(native_concept=NativeConceptCode.TEXT)

        assert anything.declares_a_structure_class is False
        assert text.declares_a_structure_class is True
        assert library.is_compatible(tested_concept=anything, wanted_concept=text) is False
        assert library.is_compatible(tested_concept=text, wanted_concept=anything) is False

    def test_get_structure_class_raises_on_an_unregistered_name(self):
        library = ConceptLibrary.make_empty()
        concept = _make_concept(code="Ghost", domain_code="nowhere", structure_class_name="GhostContentThatIsNeverRegistered")

        with pytest.raises(ConceptStructureClassNotFoundError):
            library.get_structure_class(concept=concept)

    def test_get_structure_class_returns_the_registered_class(self):
        KajsonManager.get_class_registry().register_class(UnrelatedRedContent)

        library = ConceptLibrary.make_empty()
        concept = _make_concept(code="Red", domain_code="palette", structure_class_name="UnrelatedRedContent")

        assert library.get_structure_class(concept=concept) is UnrelatedRedContent

    def test_get_structure_class_rejects_a_class_that_is_not_stuff_content(self):
        """A registered non-`StuffContent` class is as unusable as a missing one, and says so."""

        class NotAStuffContent:
            pass

        KajsonManager.get_class_registry().register_class(NotAStuffContent)

        library = ConceptLibrary.make_empty()
        concept = _make_concept(code="Bogus", domain_code="palette", structure_class_name="NotAStuffContent")

        with pytest.raises(ConceptStructureClassNotFoundError):
            library.get_structure_class(concept=concept)

    def test_native_concepts_resolve_their_structure_class(self):
        library = ConceptLibrary.make_empty_with_native_concepts()
        text_concept = library.get_native_concept(native_concept=NativeConceptCode.TEXT)

        assert library.get_structure_class(concept=text_concept).__name__ == NativeConceptCode.TEXT.structure_class_name

    def test_end_to_end_compatibility_matrix(self):
        """The composed verdict over concepts built the way the loader builds them."""
        library = ConceptLibrary.make_empty()
        concept_1 = ConceptFactory.make_from_blueprint(
            concept_code="Code1",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
        )
        concept_2 = ConceptFactory.make_from_blueprint(
            concept_code="Code2",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", refines=NativeConceptCode.TEXT),
        )
        concept_3 = ConceptFactory.make_from_blueprint(
            concept_code="Code3",
            domain_code="domain2",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", structure="TextContent"),
        )
        concept_4 = ConceptFactory.make_from_blueprint(
            concept_code="Code4",
            domain_code="domain1",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum", structure="ImageContent"),
        )
        page_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.PAGE)
        image_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE)
        visual_description = ConceptFactory.make_from_blueprint(
            concept_code="VisualDescription",
            domain_code="images",
            blueprint_or_string_description=ConceptBlueprint(description="Lorem Ipsum"),
        )

        assert library.is_compatible(tested_concept=visual_description, wanted_concept=image_concept, strict=True) is False
        assert library.is_compatible(tested_concept=visual_description, wanted_concept=image_concept, strict=False) is False

        # Both refine native Text: established by the declarations.
        assert library.is_compatible(tested_concept=concept_1, wanted_concept=concept_2) is True
        # Refining Text vs. declaring TextContent outright: the class tier settles it.
        assert library.is_compatible(tested_concept=concept_1, wanted_concept=concept_3) is True
        assert library.is_compatible(tested_concept=concept_1, wanted_concept=concept_4) is False

        # Page carries an ImageContent field: loose yes, strict no.
        assert library.is_compatible(tested_concept=page_concept, wanted_concept=image_concept, strict=False) is True
        assert library.is_compatible(tested_concept=page_concept, wanted_concept=image_concept, strict=True) is False

    def test_concept_refining_text_is_strictly_compatible_with_text(self):
        library = ConceptLibrary.make_empty()
        refining_text = ConceptFactory.make(
            domain_code="test_domain",
            concept_code="MyConceptNotNativeText",
            description="Test concept for unit tests",
            structure_class_name="TextContent",
            refines="native.Text",
        )
        text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

        assert library.is_compatible(tested_concept=refining_text, wanted_concept=text_concept, strict=True) is True
        assert library.is_compatible(tested_concept=refining_text, wanted_concept=text_concept, strict=False) is True

    def test_structurally_identical_classes_are_compatible(self):
        """Different structure class names, identical JSON structure — the class tier says yes."""
        library = ConceptLibrary.make_empty()
        text_like = ConceptFactory.make_from_blueprint(
            concept_code="MyTextLikeConcept",
            domain_code="test_structure_equiv",
            blueprint_or_string_description=ConceptBlueprint(
                description="A concept with the exact same structure as TextContent",
                structure={
                    "text": ConceptStructureBlueprint(
                        type=ConceptStructureBlueprintFieldType.TEXT,
                        description="The text content",
                        required=True,
                    ),
                },
            ),
        )
        text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)

        assert text_like.structure_class_name != text_concept.structure_class_name
        assert library.is_compatible(tested_concept=text_like, wanted_concept=text_concept, strict=True) is True
        assert library.is_compatible(tested_concept=text_like, wanted_concept=text_concept, strict=False) is True

    def test_nested_compatible_field_is_loose_only(self):
        """A class that merely *carries* a compatible value satisfies loose mode, never strict."""
        KajsonManager.get_class_registry().register_class(NestedImageInfo)
        KajsonManager.get_class_registry().register_class(DocumentWithNestedImage)

        library = ConceptLibrary.make_empty()
        with_nested_image = ConceptFactory.make(
            domain_code="test_nested",
            concept_code="DocumentWithImage",
            description="A document containing nested image info",
            structure_class_name="DocumentWithNestedImage",
        )
        image_like = ConceptFactory.make(
            domain_code="test_nested",
            concept_code="ImageInfo",
            description="Image-like info",
            structure_class_name="NestedImageInfo",
        )
        native_image = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.IMAGE)

        assert library.is_compatible(tested_concept=with_nested_image, wanted_concept=image_like, strict=True) is False
        assert library.is_compatible(tested_concept=with_nested_image, wanted_concept=image_like, strict=False) is True

        # NestedImageInfo is structurally equivalent to ImageContent.
        assert library.is_compatible(tested_concept=image_like, wanted_concept=native_image, strict=True) is True
        assert library.is_compatible(tested_concept=image_like, wanted_concept=native_image, strict=False) is True

        assert library.is_compatible(tested_concept=with_nested_image, wanted_concept=native_image, strict=True) is False
        assert library.is_compatible(tested_concept=with_nested_image, wanted_concept=native_image, strict=False) is True
