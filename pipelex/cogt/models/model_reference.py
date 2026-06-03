"""Model reference types and parsing logic for explicit prefix-based syntax.

This module provides the ModelReference type and parsing functions to disambiguate
model references using explicit prefixes:

| Type     | Sigil | Namespace (Canonical) | Example                                    |
|----------|-------|----------------------|--------------------------------------------|
| Preset   | $     | preset:              | $llm_for_creativity or preset:llm_for_creativity |
| Alias    | @     | alias:               | @best-claude or alias:best-claude          |
| Waterfall| ~     | waterfall:           | ~small-llm or waterfall:small-llm            |
| Handle   | (none)| handle: (optional)   | gpt-4o-mini or handle:gpt-4o-mini          |

BREAKING CHANGE: Bare strings (without prefix) are now treated strictly as
direct model handles. Existing configs using preset/waterfall names must add
explicit prefixes.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, model_serializer
from typing_extensions import override

from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.types import StrEnum

# Sigil prefixes for each reference kind
SIGIL_PRESET = "$"
SIGIL_ALIAS = "@"
SIGIL_WATERFALL = "~"

# Namespace prefixes for each reference kind
NAMESPACE_PRESET = "preset:"
NAMESPACE_ALIAS = "alias:"
NAMESPACE_WATERFALL = "waterfall:"
NAMESPACE_HANDLE = "handle:"


class ModelReferenceKind(StrEnum):
    """The kind of model reference."""

    PRESET = "preset"
    ALIAS = "alias"
    WATERFALL = "waterfall"
    HANDLE = "handle"


class ModelReference(BaseModel):
    """A parsed model reference with explicit kind and name.

    Args:
        kind: The type of reference (preset, alias, waterfall, or handle)
        name: The actual name of the model/preset/alias/waterfall (without prefix)
        raw: The original input string (for error messages)
    """

    model_config = ConfigDict(frozen=True)

    kind: ModelReferenceKind
    name: str
    raw: str

    @classmethod
    def parse(cls, value: str) -> "ModelReference":
        """Parse a model reference string into a ModelReference object.

        Supports both sigil prefixes ($, @, ~) and namespace prefixes (preset:, alias:, waterfall:, handle:).
        Bare strings (without any prefix) default to HANDLE.

        Args:
            value: The raw model reference string

        Returns:
            A ModelReference with the parsed kind and name

        Raises:
            ModelReferenceParseError: If the value is empty or has an empty name after prefix
        """
        if not value or not value.strip():
            msg = "Model reference cannot be empty"
            raise ModelReferenceParseError(message=msg, raw_value=value)

        value = value.strip()

        # Check for sigil prefixes first
        if value.startswith(SIGIL_PRESET):
            name = value[len(SIGIL_PRESET) :]
            if not name:
                msg = f"Preset reference '{value}' has no name after '$' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.PRESET, name=name, raw=value)

        if value.startswith(SIGIL_ALIAS):
            name = value[len(SIGIL_ALIAS) :]
            if not name:
                msg = f"Alias reference '{value}' has no name after '@' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.ALIAS, name=name, raw=value)

        if value.startswith(SIGIL_WATERFALL):
            name = value[len(SIGIL_WATERFALL) :]
            if not name:
                msg = f"Waterfall reference '{value}' has no name after '~' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.WATERFALL, name=name, raw=value)

        # Check for namespace prefixes
        if value.startswith(NAMESPACE_PRESET):
            name = value[len(NAMESPACE_PRESET) :]
            if not name:
                msg = f"Preset reference '{value}' has no name after 'preset:' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.PRESET, name=name, raw=value)

        if value.startswith(NAMESPACE_ALIAS):
            name = value[len(NAMESPACE_ALIAS) :]
            if not name:
                msg = f"Alias reference '{value}' has no name after 'alias:' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.ALIAS, name=name, raw=value)

        if value.startswith(NAMESPACE_WATERFALL):
            name = value[len(NAMESPACE_WATERFALL) :]
            if not name:
                msg = f"Waterfall reference '{value}' has no name after 'waterfall:' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.WATERFALL, name=name, raw=value)

        if value.startswith(NAMESPACE_HANDLE):
            name = value[len(NAMESPACE_HANDLE) :]
            if not name:
                msg = f"Handle reference '{value}' has no name after 'handle:' prefix"
                raise ModelReferenceParseError(message=msg, raw_value=value)
            return cls(kind=ModelReferenceKind.HANDLE, name=name, raw=value)

        # Default: bare string is treated as a direct model handle
        return cls(kind=ModelReferenceKind.HANDLE, name=value, raw=value)

    def is_preset(self) -> bool:
        """Check if this reference is a preset."""
        return self.kind == ModelReferenceKind.PRESET

    def is_alias(self) -> bool:
        """Check if this reference is an alias."""
        return self.kind == ModelReferenceKind.ALIAS

    def is_waterfall(self) -> bool:
        """Check if this reference is a waterfall."""
        return self.kind == ModelReferenceKind.WATERFALL

    def is_handle(self) -> bool:
        """Check if this reference is a direct model handle."""
        return self.kind == ModelReferenceKind.HANDLE

    @override
    def __hash__(self) -> int:
        """Make ModelReference hashable for use in sets and dict keys."""
        return hash((self.kind, self.name, self.raw))

    @model_serializer
    def serialize_to_raw_string(self) -> str:
        """Serialize ModelReference to its raw string value for TOML/JSON output."""
        return self.raw


def ensure_model_reference(value: str | ModelReference) -> ModelReference:
    """Ensure we have a ModelReference, parsing string if needed.

    Use this in code that receives `str | ModelReference` from LLMModelChoice etc.
    """
    if isinstance(value, ModelReference):
        return value
    return ModelReference.parse(value)


def parse_model_reference(value: Any) -> ModelReference | Any:
    """Pydantic BeforeValidator function to parse a string into a ModelReference.

    This function is used with Annotated types to automatically parse strings
    into ModelReference objects during Pydantic validation.

    Args:
        value: The value to parse (should be a string or ModelReference)

    Returns:
        A ModelReference object if value is a string, otherwise passes through
        the original value for Pydantic to try other union members (e.g., LLMSetting)

    Raises:
        ModelReferenceParseError: If the string value cannot be parsed
    """
    if isinstance(value, ModelReference):
        return value
    if isinstance(value, str):
        return ModelReference.parse(value)

    # Pass through other types (like dicts for LLMSetting, ExtractSetting, etc.)
    # so Pydantic can try validating them against other union members
    return value
