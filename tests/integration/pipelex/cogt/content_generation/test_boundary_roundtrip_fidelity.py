"""What survives the boundary's rebuild → dump → validate round trip, over the models that actually cross it.

The boundary arm of `revalidate_leaf_object` converts a leaf result that was built from a class
*reconstructed from JSON schema* back into the caller's own class. The rebuild names every field after the
schema's own property, so the round trip is keyed on the schema's names from end to end, and each shape
that could have lost data on the way has a test here so it stays that way: field names that shadow a
pydantic v1 method (`json`, `copy`, `schema`, `construct`), which a rebuild that renamed them once
brought back under the wrong key; plain aliases (the schema is emitted by alias, so the rebuilt field name
*is* the alias); nested models and lists; and `extra="allow"` components. Subclass erasure is unreachable
rather than safe — the rebuilt class is derived from the original's own schema, so it cannot carry a field
the original lacks — which is why there is no test for it: there is no way to construct the case through
this path.

No provider and no worker are involved, so this needs no inference marker.
"""

from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from pipelex.cogt.content_generation.object_revalidation import revalidate_leaf_object
from pipelex.cogt.content_generation.schema_to_model_factory import SchemaToModelFactory
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.core.stuffs.page_content import PageContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.core.stuffs.text_and_images_content import TextAndImagesContent


class ShadowingNames(StructuredContent):
    """Field names a caller may legitimately choose that shadow a pydantic v1 method.

    Pydantic allows them (with a warning), and the rebuild keeps them under the same names.
    """

    construct: str  # type: ignore[assignment] # pyright: ignore[reportIncompatibleMethodOverride]
    copy: str  # type: ignore[assignment] # pyright: ignore[reportIncompatibleMethodOverride]
    json: str  # type: ignore[assignment] # pyright: ignore[reportIncompatibleMethodOverride]
    schema: str  # type: ignore[assignment] # pyright: ignore[reportIncompatibleMethodOverride]


class AliasedOutput(StructuredContent):
    """A plain alias — a case the round trip already handled, kept so it keeps being handled.

    The schema ships by alias, so the rebuilt class's *field name* is `myField` with no alias of its own;
    dumping it by alias therefore emits `myField` either way, and the original validates it by alias.
    """

    my_field: str = Field(alias="myField")


def _cross_the_boundary(original: type[BaseModel], *, values: dict[str, Any]) -> BaseModel:
    """Reproduce what a worker does: rebuild the class from the shipped schema, then build an instance."""
    rebuilt = SchemaToModelFactory.make_from_json_schema(
        schema=original.model_json_schema(),
        class_name=original.__name__,
    )
    return rebuilt.model_validate(values)


class TestBoundaryRoundtripFidelity:
    def test_a_shadowing_property_comes_back_under_its_own_name(self) -> None:
        """A field named like a pydantic v1 method keeps its name through the rebuild, so it comes back under it."""
        values = {"construct": "a", "copy": "b", "json": "c", "schema": "d"}
        raw_obj = _cross_the_boundary(ShadowingNames, values=values)
        assert list(type(raw_obj).model_fields) == ["construct", "copy", "json", "schema"]

        result = revalidate_leaf_object(raw_obj, object_class=ShadowingNames, is_mock_built=False)

        assert result.construct == "a"
        assert result.copy == "b"
        assert result.json == "c"
        assert result.schema == "d"

    @pytest.mark.parametrize("dump_mode", ["python", "json"])
    def test_the_shadowing_property_survives_in_either_dump_mode(self, dump_mode: Literal["json", "python"]) -> None:
        """The distributed arm dumps in json mode, so the fix has to hold there too."""
        raw_obj = _cross_the_boundary(ShadowingNames, values={"construct": "a", "copy": "b", "json": "c", "schema": "d"})

        result = revalidate_leaf_object(raw_obj, object_class=ShadowingNames, is_mock_built=False, dump_mode=dump_mode)

        assert result.construct == "a"

    def test_a_plain_alias_round_trips(self) -> None:
        """The rebuilt field is named after the alias, which the original validates by — asserted rather than assumed."""
        raw_obj = _cross_the_boundary(AliasedOutput, values={"myField": "v"})
        assert "myField" in type(raw_obj).model_fields

        result = revalidate_leaf_object(raw_obj, object_class=AliasedOutput, is_mock_built=False)

        assert result.my_field == "v"

    @pytest.mark.parametrize(
        ("original", "values"),
        [
            (ImageContent, {"url": "https://example.com/y.png", "width": 10, "height": 20}),
            (DocumentContent, {"url": "https://example.com/y.pdf", "title": "t"}),
            (TextAndImagesContent, {"text": {"text": "hi"}, "images": [{"url": "https://example.com/y.png"}]}),
            (SearchResultContent, {"answer": "a", "sources": [{"url": "https://example.com", "title": "t"}]}),
            (PageContent, {"text_and_images": {"text": {"text": "hi"}, "images": []}, "page_view": None}),
            (CompositeContent, {"a_component": {"text": "hi"}}),
        ],
    )
    def test_native_content_classes_round_trip_without_loss(self, original: type[BaseModel], values: dict[str, Any]) -> None:
        """The classes a leaf can actually be asked to produce, including nested, list and extra-allow shapes.

        `CompositeContent` is here because it keeps its components as pydantic extras (`extra="allow"`):
        the rebuild preserves that, so the components survive rather than being dropped as unknown keys.
        """
        raw_obj = _cross_the_boundary(original, values=values)

        result = revalidate_leaf_object(raw_obj, object_class=original, is_mock_built=False)

        assert isinstance(result, original)
        assert result.model_dump(mode="json") == original.model_validate(values).model_dump(mode="json")
