"""StuffArtefact's template surface: what a string key resolves to, and what it declares to the sandbox."""

import pytest

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_artefact import BaseStuffArtefactField, StuffArtefact
from pipelex.core.stuffs.text_content import TextContent
from pipelex.tools.jinja2.template_surface import TemplateSurface, get_template_surface


def _make_artefact() -> StuffArtefact:
    return StuffArtefact(
        Stuff(
            stuff_code="note_code",
            stuff_name="note",
            concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT),
            content=TextContent(text="hello"),
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

    def test_python_code_keeps_the_wrapped_stuff(self) -> None:
        artefact = _make_artefact()
        assert artefact.stuff.content == TextContent(text="hello")


class TestTemplateSurfaceDeclaration:
    @pytest.mark.parametrize("name", ["__class__", "stuff_name"])
    def test_private_names_are_single_underscore_names(self, name: str) -> None:
        with pytest.raises(ValueError, match="single underscore"):
            TemplateSurface(callable_names=frozenset(), private_names=frozenset({name}))
