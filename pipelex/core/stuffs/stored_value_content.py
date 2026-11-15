"""The contents whose value may live in storage: `Text` (with `Markdown`), `Html` and `JSON`.

A large text travels as a reference, exactly as an image or a document does. Such a content holds either its value
(`text`, `inner_html` or `json_obj`) or a `url` to it, never both and never neither, and the referenced form carries
three facts about the value so it can describe itself without being read: its `size` in bytes as stored, its
`mime_type`, and a `preview`, the true start of the value. Those three accompany `url` only.

A referenced value is read with `load_stored_value` (`pipelex.core.stuffs.stored_value_loader`), which checks the run's
read scope exactly as an image read does, and keeps what it read in a private attribute of the content. That attribute
is never serialized, so a dump of a loaded content is still its reference, and there is never a second state on the
wire. The synchronous accessors
(`require_text`, `require_inner_html`, `require_json_obj`) and every `rendered_*` method read the value inline or
loaded, and raise :class:`StoredValueNotLoadedError` on a reference never loaded rather than printing nothing.

Loading performs IO, so only code allowed to perform IO loads: input intake, a content-generation leaf, a PipeFunc, a
direct run. Workflow code never does.

This module performs no IO and imports nothing that does, since every content class is in the kernel's import closure:
the loader lives in its own module, imported only by code that loads.

Each class declares its own fields, its value first, so its schema reads in the order the standard pins; this base
declares the reference's fields for the type checkers only, and holds the rule and the loading they share.
"""

from abc import abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from pydantic import SerializerFunctionWrapHandler, model_serializer, model_validator
from typing_extensions import override

from pipelex.core.stuffs.exceptions import StoredValueNotLoadedError
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.typing.validation_exceptions import InputFreeValueError
from pipelex.tools.uri.uri_resolver import describe_uri

# The fields of the referenced form, which accompany `url` and are absent from the inline form.
REFERENCE_METADATA_FIELDS: tuple[str, ...] = ("size", "mime_type", "preview")


class StoredValueContent(StuffContent):
    """A content holding its value inline, or a URL to it in storage."""

    if TYPE_CHECKING:
        # Declared by each subclass as a pydantic field, after its value field.
        url: str | None
        size: int | None
        mime_type: str | None
        preview: str | None

    # The name of the field holding the inline value: `text`, `inner_html` or `json_obj`.
    value_field_name: ClassVar[str]
    # The fields of the inline form, the value's first: what a rendering, a structure's or a template's, reads.
    value_form_field_names: ClassVar[tuple[str, ...]]
    # The value's kind in a description or a message: "text", "markdown", "html", "JSON".
    value_kind_desc: ClassVar[str]

    @model_validator(mode="after")
    def _validate_value_or_reference(self) -> Self:
        """A content holds its value or a URL to it, never both, never neither; the reference's metadata needs the URL."""
        class_name = self.__class__.__name__
        has_value = getattr(self, self.value_field_name) is not None
        has_url = self.url is not None
        if has_value and has_url:
            msg = f"A {class_name} holds its {self.value_field_name} or a url to it, never both."
            raise InputFreeValueError(msg)
        if not has_value and not has_url:
            msg = f"A {class_name} holds its {self.value_field_name} or a url to it, and holds neither."
            raise InputFreeValueError(msg)
        if not has_url:
            misplaced = [field_name for field_name in REFERENCE_METADATA_FIELDS if getattr(self, field_name) is not None]
            if misplaced:
                msg = f"A {class_name} holding its {self.value_field_name} inline carries no {', '.join(misplaced)}: they describe a stored value."
                raise InputFreeValueError(msg)
        # Checked here rather than as a field constraint, so the class's schema stays the pinned definition's, which has none.
        if self.size is not None and self.size < 0:
            msg = f"A {class_name}'s size counts the stored bytes and is never negative, got {self.size}."
            raise InputFreeValueError(msg)
        return self

    @override
    def __repr_args__(self) -> Sequence[tuple[str | None, Any]]:
        """Leave out the absent form's fields, so a content reads `TextContent(text='...')` as it did before it could be stored."""
        absent_form_fields = (self.value_field_name, "url", *REFERENCE_METADATA_FIELDS)
        return [
            (field_name, field_value)
            for field_name, field_value in super().__repr_args__()
            if not (field_value is None and field_name in absent_form_fields)
        ]

    @model_serializer(mode="wrap")
    def _serialize_one_form(self, handler: SerializerFunctionWrapHandler):
        """Dump the inline form without the reference's fields, and the referenced form without the value field.

        The return is left unannotated on purpose: an annotation would replace the model's serialization schema.
        """
        serialized: object = handler(self)
        if not isinstance(serialized, dict):
            return serialized
        serialized_dict = cast("dict[str, Any]", serialized)
        for field_name in (self.value_field_name, "url", *REFERENCE_METADATA_FIELDS):
            if field_name in serialized_dict and serialized_dict[field_name] is None:
                del serialized_dict[field_name]
        return serialized_dict

    @property
    def is_stored(self) -> bool:
        """Whether the value lives in storage, the content carrying its URL."""
        return self.url is not None

    @property
    def is_loaded(self) -> bool:
        """Whether the value can be read synchronously: held inline, or loaded from storage."""
        return not self.is_stored or self._has_loaded_value()

    @abstractmethod
    def _has_loaded_value(self) -> bool:
        """Whether a value loaded from storage is kept on the instance."""

    @abstractmethod
    def require_value(self) -> str | dict[str, Any]:
        """The value, held inline or loaded from storage, for a reader that does not know the content's class.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its value that was never loaded.
        """

    def rendered_value_form(self) -> dict[str, Any]:
        """The content as its inline form dumps it, a stored value read in place of its reference.

        It is what a structure holding this content renders (`ValueFormRenderable`), so a stored text inside a structure
        renders as its text, and one never loaded refuses to render.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its value that was never loaded.
        """
        return {
            field_name: self.require_value() if field_name == self.value_field_name else getattr(self, field_name)
            for field_name in self.value_form_field_names
        }

    @abstractmethod
    def accept_loaded_text(self, *, text: str) -> None:
        """Keep the value read from storage, given as the text it was stored as, so the content can be read synchronously.

        The model's fields are left unchanged, so a dump is still the reference. A content holding its value inline
        has nothing to keep.

        Raises:
            StoredValueUnreadableError: The text is not a value of the content's kind.
        """

    def _make_not_loaded_error(self) -> StoredValueNotLoadedError:
        url_desc = describe_uri(self.url) if self.url is not None else "nowhere"
        msg = (
            f"This {self.__class__.__name__} holds a reference to its {self.value_field_name} ({url_desc}, {self._size_desc()}), "
            "which was never loaded. Code that can read storage loads it with `await load_stored_value(content, ...)` before reading or rendering it."
        )
        return StoredValueNotLoadedError(msg)

    def _size_desc(self) -> str:
        if self.size is None:
            return "size unknown"
        return f"{self.size} bytes"

    def _stored_short_desc(self) -> str:
        return f"some stored {self.value_kind_desc} ({self._size_desc()})"
