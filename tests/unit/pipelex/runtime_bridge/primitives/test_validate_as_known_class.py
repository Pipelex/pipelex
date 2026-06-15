from pydantic import ConfigDict

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.runtime_bridge.primitives.hydration import _validate_as_known_class  # noqa: PLC2701  # pyright: ignore[reportPrivateUsage]


class _StuffContentAllowExtra(StuffContent):
    # extra="allow" lets us observe whether nested subclass-specific data
    # made it into the dump that the function feeds into model_validate.
    model_config = ConfigDict(extra="allow")


class _SpecificMeta(_StuffContentAllowExtra):
    flavor: str


class _OuterContent(StuffContent):
    meta: _StuffContentAllowExtra


class _RebuiltOuterContent(StuffContent):
    # Same shape as _OuterContent but a distinct Python class object — stands in
    # for the "rebuilt after re-exec" class identity in the cross-exec scenario.
    meta: _StuffContentAllowExtra


class TestValidateAsKnownClass:
    def test_returns_instance_when_class_identity_matches(self) -> None:
        """When type(raw_item) is item_class, return the instance as-is (no round-trip)."""
        instance = TextContent(text="hello")
        result = _validate_as_known_class(item_class=TextContent, raw_item=instance)
        assert result is instance

    def test_validates_dict_input(self) -> None:
        """When raw_item is a dict, validate it through model_validate."""
        result = _validate_as_known_class(item_class=TextContent, raw_item={"text": "hello"})
        assert isinstance(result, TextContent)
        assert result.text == "hello"

    def test_cross_exec_round_trip_basic(self) -> None:
        """Cross-exec instance (different class identity, same shape) round-trips correctly."""
        original = _OuterContent(meta=_StuffContentAllowExtra())
        result = _validate_as_known_class(item_class=_RebuiltOuterContent, raw_item=original)
        assert type(result) is _RebuiltOuterContent

    def test_cross_exec_preserves_nested_subclass_data(self) -> None:
        """Cross-exec round-trip preserves subclass-specific data in nested base-typed fields.

        The nested ``meta`` field is annotated as ``_StuffContentAllowExtra`` but holds a
        ``_SpecificMeta`` instance carrying an extra ``flavor`` field. ``smart_dump``
        uses ``serialize_as_any=True`` so the dump reflects the runtime type and keeps
        ``flavor``. Plain ``model_dump`` would dump using the field annotation and drop
        ``flavor`` before validation ever sees it — so this assertion would fail if the
        implementation regressed back to ``model_dump()``.
        """
        instance = _OuterContent(meta=_SpecificMeta(flavor="vanilla"))
        result = _validate_as_known_class(item_class=_RebuiltOuterContent, raw_item=instance)

        assert type(result) is _RebuiltOuterContent
        extras = result.meta.model_extra or {}
        assert extras.get("flavor") == "vanilla", (
            f"Nested subclass field 'flavor' was lost in the cross-exec round-trip — "
            f"likely a regression from smart_dump() back to model_dump() without "
            f"serialize_as_any=True. result.meta.model_extra={result.meta.model_extra}"
        )
