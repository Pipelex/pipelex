"""Shared fixture classes for the object-mock fidelity tests (dry-run fidelity arms)."""

from pydantic import field_validator

from pipelex.core.stuffs.structured_content import StructuredContent


class ConstrainedName(StructuredContent):
    """Original class with an invariant the JSON-schema round-trip cannot capture."""

    name: str

    @field_validator("name")
    @classmethod
    def _require_prefix(cls, value: str) -> str:
        if not value.startswith("PFX_"):
            msg = "name must start with 'PFX_'"
            raise ValueError(msg)
        return value


class PlainName(StructuredContent):
    """Control class whose only constraint (a plain string field) survives the round-trip."""

    name: str
