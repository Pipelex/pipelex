"""Concept endpoint — convert JSON concept spec to TOML."""

import json
from typing import Any

from fastapi import APIRouter
from pipelex.builder.operations.concept_ops import concept_spec_to_toml, parse_concept_spec
from pydantic import BaseModel, Field, ValidationError, field_validator

from pipelex_api.errors import raise_validation_error
from pipelex_api.json_body import JsonBodyRoute
from pipelex_api.limits import MAX_AGENT_SPEC_BYTES

router = APIRouter(tags=["agent"], route_class=JsonBodyRoute)


class BuildConceptRequest(BaseModel):
    spec: dict[str, Any] = Field(..., description="JSON concept specification.")

    @field_validator("spec")
    @classmethod
    def _bound_spec_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value).encode("utf-8")) > MAX_AGENT_SPEC_BYTES:
            msg = f"spec exceeds {MAX_AGENT_SPEC_BYTES // 1024} KiB limit"
            raise ValueError(msg)
        return value


class BuildConceptResponse(BaseModel):
    success: bool = Field(default=True, description="Whether the operation was successful")
    concept_code: str = Field(..., description="The concept code that was generated")
    toml: str = Field(..., description="Generated TOML content for the concept")


@router.post("/build/concept")
async def build_concept(request_data: BuildConceptRequest) -> BuildConceptResponse:
    """Convert a JSON concept spec to TOML format.

    A malformed spec surfaces as a Pydantic `ValidationError` — an API-owned
    422. Pipelex domain failures propagate untouched to the global
    `PipelexError` handler in `pipelex_api.exception_handlers`.

    A malformed shape — a non-mapping `structure` (`{"structure": "string"}`)
    or a `structure` field that is neither a string nor a mapping
    (`{"structure": {"f": 42}}`) — is refused by `parse_concept_spec` itself
    with a typed `ConceptSpecError`, which that same handler answers. Nothing
    broader is caught here: a bare exception from pipelex is the signal of a
    real programming bug, and a route-level catch would mask it.
    """
    try:
        concept_spec = parse_concept_spec(request_data.spec)
        toml_content = concept_spec_to_toml(concept_spec)

        return BuildConceptResponse(
            success=True,
            concept_code=concept_spec.concept_code,
            toml=toml_content,
        )
    except ValidationError as exc:
        raise_validation_error(message=str(exc))
