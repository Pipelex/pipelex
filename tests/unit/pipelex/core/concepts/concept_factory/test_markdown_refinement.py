import pytest

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.markdown_content import MarkdownContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.libraries.concept.concept_library import ConceptLibrary


def _make_concept(*, code: str, blueprint: ConceptBlueprint | str) -> Concept:
    return ConceptFactory.make_from_blueprint(domain_code="site_reports", concept_code=code, blueprint_or_string_description=blueprint)


class TestMarkdownRefinement:
    def test_native_markdown_refines_native_text(self):
        """The native Markdown concept declares its refinement of Text and resolves MarkdownContent."""
        markdown = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.MARKDOWN)
        assert markdown.concept_ref == "native.Markdown"
        assert markdown.refines == NativeConceptCode.TEXT.concept_ref
        assert markdown.structure_class_name == "MarkdownContent"
        assert NativeConceptCode.MARKDOWN.structure_class is MarkdownContent
        assert NativeConceptCode.MARKDOWN.refined_native is NativeConceptCode.TEXT
        assert NativeConceptCode.is_text_concept("Markdown")

        library = ConceptLibrary.make_empty()
        assert library.get_structure_class(concept=markdown) is MarkdownContent

    @pytest.mark.parametrize("native_code", list(NativeConceptCode))
    def test_the_factory_declares_exactly_the_enum_refinements(self, native_code: NativeConceptCode):
        """`refines` on a native concept is the enum's `refined_native`, and nothing else."""
        refined_native = native_code.refined_native
        expected_refines = refined_native.concept_ref if refined_native else None
        assert ConceptFactory.make_native_concept(native_concept_code=native_code).refines == expected_refines

    def test_refining_markdown_resolves_markdown_content(self):
        """`refines = "Markdown"` builds a concept whose structure class inherits from MarkdownContent."""
        concept = _make_concept(code="SiteReport", blueprint=ConceptBlueprint(description="A site report", refines="Markdown"))
        structure_class = ConceptLibrary.make_empty().get_structure_class(concept=concept)
        assert issubclass(structure_class, MarkdownContent)
        assert concept.refines == NativeConceptCode.MARKDOWN.concept_ref

    @pytest.mark.parametrize("strict", [True, False])
    def test_markdown_is_accepted_where_text_is_wanted(self, strict: bool):
        """Markdown refines Text, so a Markdown value stands in for a Text, strictly or loosely."""
        library = ConceptLibrary.make_empty_with_native_concepts()
        markdown = library.get_native_concept(native_concept=NativeConceptCode.MARKDOWN)
        text = library.get_native_concept(native_concept=NativeConceptCode.TEXT)
        assert library.is_compatible(tested_concept=markdown, wanted_concept=text, strict=strict) is True

    @pytest.mark.parametrize("strict", [True, False])
    def test_text_is_refused_where_markdown_is_wanted(self, strict: bool):
        """A plain Text, or any text concept beside Markdown, is not a Markdown, although its class has the same shape."""
        library = ConceptLibrary.make_empty_with_native_concepts()
        markdown = library.get_native_concept(native_concept=NativeConceptCode.MARKDOWN)
        text = library.get_native_concept(native_concept=NativeConceptCode.TEXT)
        description_only = _make_concept(code="SiteNote", blueprint="A note taken on site")
        refining_text = _make_concept(code="SiteSummary", blueprint=ConceptBlueprint(description="A summary", refines="Text"))
        declaring_text_content = _make_concept(code="SiteLine", blueprint=ConceptBlueprint(description="A line", structure="TextContent"))

        for tested in (text, description_only, refining_text, declaring_text_content):
            assert library.is_compatible(tested_concept=tested, wanted_concept=markdown, strict=strict) is False, tested.concept_ref

    @pytest.mark.parametrize("strict", [True, False])
    def test_markdown_lineage_is_accepted_at_any_depth(self, strict: bool):
        """A concept refining Markdown, directly or through another concept, is a Markdown, and so a Text."""
        library = ConceptLibrary.make_empty_with_native_concepts()
        site_report = _make_concept(code="SiteReport", blueprint=ConceptBlueprint(description="A site report", refines="Markdown"))
        library.add_new_concept(concept=site_report)
        roof_report = _make_concept(code="RoofReport", blueprint=ConceptBlueprint(description="A roof report", refines="SiteReport"))
        markdown = library.get_native_concept(native_concept=NativeConceptCode.MARKDOWN)
        text = library.get_native_concept(native_concept=NativeConceptCode.TEXT)

        for tested in (site_report, roof_report):
            assert library.is_compatible(tested_concept=tested, wanted_concept=markdown, strict=strict) is True, tested.concept_ref
            assert library.is_compatible(tested_concept=tested, wanted_concept=text, strict=strict) is True, tested.concept_ref
        assert issubclass(library.get_structure_class(concept=roof_report), MarkdownContent)

    def test_markdown_is_accepted_where_a_text_refinement_is_wanted(self):
        """Wherever a Text is accepted, a Markdown is: the relation between Text and its refinements is unchanged."""
        library = ConceptLibrary.make_empty_with_native_concepts()
        markdown = library.get_native_concept(native_concept=NativeConceptCode.MARKDOWN)
        text = library.get_native_concept(native_concept=NativeConceptCode.TEXT)
        refining_text = _make_concept(code="SiteSummary", blueprint=ConceptBlueprint(description="A summary", refines="Text"))

        assert library.is_compatible(tested_concept=text, wanted_concept=refining_text, strict=True) is True
        assert library.is_compatible(tested_concept=markdown, wanted_concept=refining_text, strict=True) is True
        assert issubclass(library.get_structure_class(concept=refining_text), TextContent)
