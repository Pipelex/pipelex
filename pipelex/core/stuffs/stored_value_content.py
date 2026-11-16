"""The contents whose value may live in storage: `Text` (with `Markdown`), `Html` and `JSON`.

A large text travels as a reference, exactly as an image or a document does. Such a content holds either its value
(`text`, `inner_html` or `json_obj`) or a `url` to it, never both and never neither, and the referenced form carries
three facts about the value so it can describe itself without being read: its `size` in bytes as stored, its
`mime_type`, and a `preview`, the true start of the value. Those three accompany `url` only.

A referenced value is read with `load_stored_value` (`pipelex.core.stuffs.stored_value_loader`), which checks the run's
read scope exactly as an image read does, and keeps what it read in a private attribute of the content. That attribute
is never serialized, so a dump of a loaded content is still its reference, and there is never a second state on the
wire. `require_value` and the typed accessors built on it (`require_text`, `require_inner_html`, `require_json_obj`),
and every `rendered_*` method, read the value inline or loaded, and raise :class:`StoredValueNotLoadedError` on a
reference never loaded rather than printing nothing.

Loading performs IO, so only code allowed to perform IO loads: input intake, a content-generation leaf, a PipeFunc, a
direct run. Workflow code never does.

This module performs no IO and imports nothing that does, since every content class is in the kernel's import closure:
the loader lives in its own module, imported only by code that loads.

Each class declares its own fields, its value first, so its schema reads in the order the standard pins; this base
declares the reference's fields for the type checkers only, and holds the rule, the loaded value and the reading they
share. A class whose stored text is not its value as it is overrides `_decode_loaded_text` (`JSONContent` parses it).

A model generating a content never generates a reference: it writes the value. So the JSON schema a structured
generation hands the model, or carries to a leaf that rebuilds the class from it, is written under
`generation_schema()`, where a stored-value content's schema leaves out `url`, `size`, `mime_type` and `preview` and
requires its value. Anywhere else, such as a pipe's input contract, the schema keeps both forms, as the standard pins.
"""

from collections.abc import Generator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

from pydantic import GetJsonSchemaHandler, PrivateAttr, SerializerFunctionWrapHandler, model_serializer, model_validator
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema
from typing_extensions import override

from pipelex.core.stuffs.exceptions import StoredValueNotLoadedError
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.tools.misc.pretty import require_rich_for_rendering
from pipelex.tools.typing.validation_exceptions import InputFreeValueError
from pipelex.tools.uri.uri_resolver import describe_uri

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable

# The fields of the referenced form, which accompany `url` and are absent from the inline form.
REFERENCE_METADATA_FIELDS: tuple[str, ...] = ("size", "mime_type", "preview")
# Every field of the referenced form, `url` first: where the value is and what describes it, never a part of the value.
# The pinned natives, the input templates and the dry-run mocks all read this one list.
STORED_VALUE_REFERENCE_FIELDS: tuple[str, ...] = ("url", *REFERENCE_METADATA_FIELDS)

# The value read from storage: a text, or the object a JSON content parses its text into.
StoredValue = str | dict[str, Any]

# Whether the JSON schema being written is one a model generates from, set by `generation_schema()`.
_IS_GENERATION_SCHEMA: ContextVar[bool] = ContextVar("is_generation_schema", default=False)


@contextmanager
def generation_schema() -> Generator[None, None, None]:
    """Write the JSON schemas of the block as a model generates from them: a stored-value content as its value alone.

    A structured generation's schema, the one a provider shows the model and the one an object assignment carries to a
    leaf that rebuilds the class from it, is written under it, so the model is never asked for a `url`, and a class
    rebuilt from the schema, which loses the rule that a content holds its value or a URL, never both, has no `url` for a
    dry run's mock to fill beside the value.
    """
    token = _IS_GENERATION_SCHEMA.set(True)
    try:
        yield
    finally:
        _IS_GENERATION_SCHEMA.reset(token)


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
    # The MIME type a value of this class is stored under, and the extension its storage key ends with: what the code
    # that stores a large value (`pipelex.core.stuffs.stored_value_storer`) writes.
    stored_mime_type: ClassVar[str]
    stored_file_extension: ClassVar[str]

    # The value read from storage for a referenced content, never serialized.
    _loaded_value: StoredValue | None = PrivateAttr(default=None)

    # The JSON schema hook below changes the schema only under `generation_schema()`, so a schema comparison, which runs
    # outside it, may treat the class as one that keeps pydantic's own schema (`SCHEMA_NEUTRAL_HOOKS_ATTRIBUTE`).
    __schema_neutral_hooks__: ClassVar[tuple[str, ...]] = ("__get_pydantic_json_schema__",)

    @classmethod
    @override
    def __get_pydantic_json_schema__(cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler) -> JsonSchemaValue:
        """The class's JSON schema; under `generation_schema()`, its value alone, required, without the reference's fields."""
        json_schema = super().__get_pydantic_json_schema__(core_schema, handler)
        if not _IS_GENERATION_SCHEMA.get():
            return json_schema
        model_schema = handler.resolve_ref_schema(json_schema)
        properties: dict[str, Any] = model_schema.get("properties", {})
        for field_name in STORED_VALUE_REFERENCE_FIELDS:
            properties.pop(field_name, None)
        value_schema: dict[str, Any] | None = properties.get(cls.value_field_name)
        if value_schema is not None:
            value_schema.pop("default", None)
            any_of: list[dict[str, Any]] | None = value_schema.get("anyOf")
            if any_of is not None:
                non_null_schemas = [branch_schema for branch_schema in any_of if branch_schema.get("type") != "null"]
                if len(non_null_schemas) == 1:
                    del value_schema["anyOf"]
                    value_schema.update(non_null_schemas[0])
                else:
                    value_schema["anyOf"] = non_null_schemas
        required: list[str] = [field_name for field_name in model_schema.get("required", []) if field_name not in STORED_VALUE_REFERENCE_FIELDS]
        if cls.value_field_name in properties and cls.value_field_name not in required:
            required.insert(0, cls.value_field_name)
        model_schema["required"] = required
        return json_schema

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
    def __setattr__(self, name: str, value: Any) -> None:
        """Assigning the value makes the content hold it inline, so it is never in both forms at once.

        A PipeFunc that rewrites a loaded reference (`note.text = note.require_text().upper()`) gets an inline content:
        the reference and its size, MIME type and preview described the value it replaces, so they are cleared, and so
        is the value loaded from it. Construction does not pass through here; the model validator checks it instead.
        """
        if name == self.value_field_name and value is not None:
            if self.url is not None:
                for field_name in STORED_VALUE_REFERENCE_FIELDS:
                    super().__setattr__(field_name, None)
            self._loaded_value = None
        super().__setattr__(name, value)

    @override
    def __repr_args__(self) -> Sequence[tuple[str | None, Any]]:
        """Leave out the absent form's fields, so a content reads `TextContent(text='...')` as it did before it could be stored."""
        absent_form_fields = (self.value_field_name, *STORED_VALUE_REFERENCE_FIELDS)
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
        for field_name in (self.value_field_name, *STORED_VALUE_REFERENCE_FIELDS):
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
        return not self.is_stored or self._loaded_value is not None

    def is_value_field(self, *, field_name: str) -> bool:
        """Whether a field is the one holding the value inline, which a reader reads through `require_value` (`ValueFieldReadable`)."""
        return field_name == self.value_field_name

    def require_value(self) -> StoredValue:
        """The value, held inline or loaded from storage, for a reader that does not know the content's class.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its value that was never loaded.
        """
        inline_value: StoredValue | None = getattr(self, self.value_field_name)
        if inline_value is not None:
            return inline_value
        if self._loaded_value is not None:
            return self._loaded_value
        raise self._make_not_loaded_error()

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

    def stored_text(self) -> str:
        """The text an inline value is stored as, which `size` measures and `preview` starts: the value itself, for a text or HTML.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its value that was never loaded.
        """
        value = self.require_value()
        if not isinstance(value, str):
            msg = f"A {self.__class__.__name__} holds a value that is not a text, and must say how it is stored."
            raise TypeError(msg)
        return value

    def accept_storage(self, *, url: str, size: int, mime_type: str, preview: str) -> None:
        """Turn this inline content into its reference to the value just stored, keeping the value loaded.

        The code that stored the value calls it, in place, so every holder of the content sees the reference, a dump of it
        is the reference alone, and a reader in the same process still reads the value without loading it again.

        Args:
            url: Where the value was stored.
            size: The stored value's length in bytes.
            mime_type: The MIME type it was stored under.
            preview: The true start of the value.
        """
        value = self.require_value()
        # Through pydantic's own assignment, below this class's, which would clear the loaded value on assigning the value.
        super().__setattr__(self.value_field_name, None)
        super().__setattr__("url", url)
        super().__setattr__("size", size)
        super().__setattr__("mime_type", mime_type)
        super().__setattr__("preview", preview)
        self._loaded_value = value

    def hold_value_inline(self) -> None:
        """Turn this content into its inline form, holding its value, inline or loaded, and dropping any reference.

        For a process handing the content to one that reaches no storage, such as a host dispatching a PipeFunc call to a
        sandbox: a dump of it is then the value itself.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its value that was never loaded.
        """
        if self.url is None:
            return
        # Assigning the value clears the reference and its metadata (`__setattr__`).
        setattr(self, self.value_field_name, self.require_value())

    def accept_loaded_text(self, *, text: str) -> None:
        """Keep the value read from storage, given as the text it was stored as, so the content can be read synchronously.

        The model's fields are left unchanged, so a dump is still the reference. A content holding its value inline
        has nothing to keep.

        Raises:
            StoredValueUnreadableError: The text is not a value of the content's kind.
        """
        if self.url is None:
            return
        self._loaded_value = self._decode_loaded_text(text=text)

    def _decode_loaded_text(self, *, text: str) -> StoredValue:
        """The value a stored text holds: the text itself, for a text or HTML content.

        Raises:
            StoredValueUnreadableError: The text is not a value of the content's kind.
        """
        return text

    def rendered_reference_pretty(self) -> "PrettyPrintable":
        """What a pretty print shows of a stored value never loaded: its kind, size, location and preview.

        A pretty print is a display, made where storage may not be reachable, such as a terminal printing a hosted run's
        output, so it describes the reference rather than refusing it, as a render for a reader does.
        """
        require_rich_for_rendering()
        from rich.text import Text

        described = Text(self.reference_summary())
        if self.preview:
            described.append(f"\nIt starts: {self.preview}")
        return described

    def reference_summary(self) -> str:
        """One sentence describing a stored value never loaded, from its reference alone: its kind, size and location.

        What a render for a person shows in place of the value when it cannot be loaded, beside the `preview`.
        """
        url_desc = describe_uri(self.url) if self.url is not None else "nowhere"
        return f"{self._stored_short_desc().capitalize()}, stored at {url_desc}, not loaded."

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
