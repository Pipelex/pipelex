import json
from typing import TYPE_CHECKING, Any, ClassVar, cast

from json2html import json2html
from pydantic import Field, field_validator
from typing_extensions import override

from pipelex.core.stuffs.exceptions import StoredValueUnreadableError
from pipelex.core.stuffs.stored_value_content import StoredValue, StoredValueContent
from pipelex.tools.misc.filetype_utils import base_mime_type
from pipelex.tools.misc.markdown_utils import convert_to_markdown
from pipelex.tools.misc.pretty import require_rich_for_rendering
from pipelex.tools.typing.validation_exceptions import InputFreeValueError

if TYPE_CHECKING:
    from pipelex.tools.misc.pretty import PrettyPrintable

JSON_MIME_TYPE = "application/json"


def is_json_mime_type(*, mime_type: str) -> bool:
    """Whether a MIME type names JSON: `application/json`, or a structured syntax suffix such as `application/ld+json`."""
    bare_mime_type = base_mime_type(mime_type=mime_type)
    return bare_mime_type == JSON_MIME_TYPE or bare_mime_type.endswith("+json")


# TODO: use pipelex.tools.misc.json_utils.JsonContent to support lists in addition to dicts
class JSONContent(StoredValueContent):
    value_field_name: ClassVar[str] = "json_obj"
    value_form_field_names: ClassVar[tuple[str, ...]] = ("json_obj",)
    value_kind_desc: ClassVar[str] = "JSON"

    json_obj: dict[str, Any] | None = Field(default=None, description="The JSON object")
    url: str | None = Field(default=None, description="The URL of the stored JSON object: a storage URI, an HTTP(S) URL, or a base64 data URL")
    size: int | None = Field(default=None, description="The length of the stored JSON object's serialized form, in bytes as stored")
    mime_type: str | None = Field(default=None, description="The MIME type of the stored JSON object: application/json")
    preview: str | None = Field(
        default=None, description="The first few hundred characters of the stored JSON object's serialized form, always its true start"
    )

    @field_validator("json_obj", mode="before")
    @classmethod
    def check_valid_json(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        # A ValueError, never a TypeError: pydantic turns only the former into a ValidationError, so a
        # dict holding a value that is not JSON is reported like any other invalid content. NaN and the
        # infinities are refused too, since JSON cannot hold them and serialization would turn them into null.
        # The encoder's complaint names a type, a circular reference or an out-of-range float, never the value.
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            msg = f"json_obj is not valid JSON: {exc}"
            raise InputFreeValueError(msg) from exc
        return value

    @override
    def _decode_loaded_text(self, *, text: str) -> StoredValue:
        """The stored JSON, decoded by its MIME type: a JSON type, or none declared, is parsed back into its object.

        Raises:
            StoredValueUnreadableError: The stored value declares a type that is not JSON, or is not a JSON object.
        """
        if self.mime_type is not None and not is_json_mime_type(mime_type=self.mime_type):
            msg = f"A stored JSON value declares the MIME type '{self.mime_type}', which is not JSON."
            raise StoredValueUnreadableError(msg)
        try:
            decoded: Any = json.loads(text)
        except json.JSONDecodeError as exc:
            msg = f"A stored JSON value is not valid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}."
            raise StoredValueUnreadableError(msg) from exc
        if not isinstance(decoded, dict):
            msg = f"A stored JSON value is a JSON {type(decoded).__name__}, and a JSON content holds an object."
            raise StoredValueUnreadableError(msg)
        return cast("dict[str, Any]", decoded)

    def require_json_obj(self) -> dict[str, Any]:
        """The JSON object, held inline or loaded from storage.

        Raises:
            StoredValueNotLoadedError: The content holds a reference to its JSON that was never loaded.
        """
        # A JSON content's value is its `json_obj` field, or the object its stored text decodes into, so it is always a dict.
        return cast("dict[str, Any]", self.require_value())

    @property
    @override
    def short_desc(self) -> str:
        if self.json_obj is None:
            return self._stored_short_desc()
        return super().short_desc

    @override
    def rendered_html(self) -> str:
        html: str = json2html.convert(  # pyright: ignore[reportAssignmentType, reportUnknownVariableType]
            json=self.require_json_obj(),  # pyright: ignore[reportArgumentType]
            clubbing=True,
            table_attributes="",
        )
        return html

    @override
    def rendered_markdown(self, *, level: int = 1, is_pretty: bool = False) -> str:
        return convert_to_markdown(data=self.require_json_obj(), level=level, is_pretty=is_pretty)

    @override
    def rendered_plain(self) -> str:
        return json.dumps(self.require_json_obj(), indent=4)

    @override
    def rendered_json(self) -> str:
        return json.dumps(self.require_json_obj(), indent=4)

    @override
    def rendered_pretty(self, *, title: str | None = None, depth: int = 0) -> "PrettyPrintable":
        require_rich_for_rendering()
        from rich.json import JSON

        return JSON.from_data(self.require_json_obj(), indent=4)
