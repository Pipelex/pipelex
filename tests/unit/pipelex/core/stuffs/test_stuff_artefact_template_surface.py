"""StuffArtefact's template surface: what a string key resolves to, and what it declares to the sandbox."""

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import BaseStuffArtefactField, StuffArtefact, unwrap_stuff_artefact
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.template_surface import get_template_surface


def _make_artefact() -> StuffArtefact:
    return StuffArtefact(
        Stuff(
            stuff_code="note_code",
            stuff_name="note",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="hello"),
        )
    )


def _make_composite_artefact() -> StuffArtefact:
    return StuffArtefact(
        Stuff(
            stuff_code="combo_code",
            stuff_name="combo",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.COMPOSITE),
            content=CompositeContent.model_validate(
                {"summary": TextContent(text="S"), "title": TextContent(text="T"), "_hidden": TextContent(text="H")}
            ),
        )
    )


class TestStuffArtefactTemplateSurface:
    def test_declares_its_accessors_and_metadata(self) -> None:
        surface = get_template_surface(_make_artefact())
        assert surface is not None
        assert surface.callable_names == frozenset({"get", "iter_keys", "iter_items", "iter_values"})
        assert surface.private_names == frozenset({"_stuff_name", "_content_class", "_concept_code", "_stuff_code"})

    @pytest.mark.parametrize("key", ["_stuff", "_content", "__class__", "stuff", "get", "render_with_images", "missing"])
    def test_bracket_key_resolves_only_to_fields_and_metadata(self, key: str) -> None:
        with pytest.raises(KeyError):
            _ = _make_artefact()[key]

    @pytest.mark.parametrize("key", ["_stuff", "_content", "stuff", "iter_keys"])
    def test_get_resolves_only_to_fields_and_metadata(self, key: str) -> None:
        assert _make_artefact().get(key, default="absent") == "absent"

    def test_bracket_key_reads_fields_and_metadata(self) -> None:
        artefact = _make_artefact()
        assert artefact["text"] == "hello"
        assert artefact[BaseStuffArtefactField.STUFF_NAME] == "note"
        assert artefact[BaseStuffArtefactField.CONTENT_CLASS] == "TextContent"
        assert artefact[BaseStuffArtefactField.CONCEPT_CODE] == "Text"
        assert artefact[BaseStuffArtefactField.STUFF_CODE] == "note_code"

    def test_raw_content_is_not_a_key(self) -> None:
        artefact = _make_artefact()
        assert "_content" not in artefact
        assert "_content" not in list(artefact.iter_keys())

    def test_wrapped_stuff_is_not_an_attribute(self) -> None:
        artefact = _make_artefact()
        assert not hasattr(artefact, "stuff")
        assert "stuff" not in artefact

    def test_python_code_unwraps_the_stuff(self) -> None:
        artefact = _make_artefact()
        assert unwrap_stuff_artefact(artefact=artefact).content == TextContent(text="hello")

    def test_composite_parts_are_fields(self) -> None:
        """A Composite holds its parts as extra fields of the model: they resolve like declared fields."""
        artefact = _make_composite_artefact()
        assert artefact["summary"] == TextContent(text="S")
        assert artefact.get("title") == TextContent(text="T")
        assert "summary" in artefact
        assert list(artefact.iter_keys())[:2] == ["summary", "title"]

    def test_composite_part_named_like_a_pydantic_attribute_is_the_part(self) -> None:
        artefact = StuffArtefact(
            Stuff(
                stuff_code="clash_code",
                stuff_name="clash",
                concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.COMPOSITE),
                content=CompositeContent.model_validate({"model_extra": TextContent(text="E"), "model_dump": TextContent(text="D")}),
            )
        )
        assert artefact["model_extra"] == TextContent(text="E")
        assert artefact.get("model_dump") == TextContent(text="D")

    def test_private_composite_part_is_not_a_field(self) -> None:
        artefact = _make_composite_artefact()
        assert "_hidden" not in artefact
        assert "_hidden" not in list(artefact.iter_keys())
        with pytest.raises(KeyError):
            _ = artefact["_hidden"]
