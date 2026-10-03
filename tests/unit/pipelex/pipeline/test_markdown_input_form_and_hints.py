import pytest

from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.core.domains.domain_blueprint import DomainBlueprint
from pipelex.libraries.crate_qualification import qualify_crate
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.pipeline.hint_warnings import build_hint_warnings
from pipelex.pipeline.input_form import FieldKind, FormPosition, InputFormDeriver

_CONCEPTS: dict[str, ConceptBlueprint | str] = {
    # A report refining native Markdown, which refines Text: text-valued, so `label` applies.
    "docs.Report": ConceptBlueprint(description="a report", refines="native.Markdown", hints={"intent": "label"}),
    # Declaring the Markdown content class outright maps by identity to the native Markdown row.
    "docs.Minutes": ConceptBlueprint(description="meeting minutes", structure="MarkdownContent", hints={"intent": "prose"}),
}


class TestMarkdownInputFormAndHints:
    def test_native_markdown_is_prose(self):
        """A Markdown input is typed as its source, like a Text one: a `prose` node."""
        node = InputFormDeriver(concepts={}, position=FormPosition.INPUT).derive_concept(name="report", concept_ref="native.Markdown")
        assert node.kind is FieldKind.PROSE
        assert node.concept_ref == "native.Markdown"

    @pytest.mark.parametrize(
        ("concept_ref", "expected_kind"),
        [
            ("docs.Report", FieldKind.TEXT),
            ("docs.Minutes", FieldKind.PROSE),
        ],
    )
    def test_markdown_chains_are_text_valued_sites(self, concept_ref: str, expected_kind: FieldKind):
        """An intent word applies to a Markdown-backed concept, in the descriptor and in the lint alike."""
        node = InputFormDeriver(concepts=dict(_CONCEPTS), position=FormPosition.INPUT).derive_concept(name="field", concept_ref=concept_ref)
        assert node.kind is expected_kind

        crate = LibraryCrate(
            concepts=dict(_CONCEPTS),
            pipes={},
            domains={"docs": DomainBlueprint(code="docs", description="Docs domain")},
            source_map={},
        )
        assert build_hint_warnings(qualify_crate(crate)) == []
