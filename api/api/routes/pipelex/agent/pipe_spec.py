"""Pipe spec endpoint — convert JSON pipe spec to TOML."""

import json
from typing import Any

from fastapi import APIRouter
from pipelex.builder.operations.pipe_ops import parse_pipe_spec, pipe_spec_to_toml
from pydantic import BaseModel, Field, ValidationError, field_validator

from api.errors import raise_validation_error
from api.limits import MAX_AGENT_SPEC_BYTES

router = APIRouter(tags=["agent"])


class BuildPipeSpecRequest(BaseModel):
    pipe_type: str = Field(..., min_length=1, max_length=128, description="The pipe type (e.g. PipeLLM, PipeSequence, etc.).")
    spec: dict[str, Any] = Field(..., description="JSON pipe specification.")

    @field_validator("spec")
    @classmethod
    def _bound_spec_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        if len(json.dumps(value).encode("utf-8")) > MAX_AGENT_SPEC_BYTES:
            msg = f"spec exceeds {MAX_AGENT_SPEC_BYTES // 1024} KiB limit"
            raise ValueError(msg)
        return value


class BuildPipeSpecResponse(BaseModel):
    success: bool = Field(default=True, description="Whether the operation was successful")
    pipe_code: str = Field(..., description="The pipe code that was generated")
    pipe_type: str = Field(..., description="The pipe type")
    toml: str = Field(..., description="Generated TOML content for the pipe")


@router.post("/build/pipe-spec")
async def build_pipe_spec(request_data: BuildPipeSpecRequest) -> BuildPipeSpecResponse:
    """Convert a JSON pipe spec to TOML format.

    Two caller-mistake paths surface as a 422 here: a `ValidationError` from
    Pydantic when the spec shape doesn't match the chosen pipe type, and a
    `ValueError` from `parse_pipe_spec` when `pipe_type` is not one of the
    known pipe types (documented in `parse_pipe_spec`'s docstring; raised at
    exactly one site). Pipelex domain failures propagate untouched to the
    global `PipelexError` handler in `api.exception_handlers`.
    """
    try:
        pipe_spec = parse_pipe_spec(request_data.spec, pipe_type=request_data.pipe_type)
        toml_content = pipe_spec_to_toml(pipe_spec)

        return BuildPipeSpecResponse(
            success=True,
            pipe_code=pipe_spec.pipe_code,
            pipe_type=request_data.pipe_type,
            toml=toml_content,
        )
    except (ValidationError, ValueError) as exc:
        raise_validation_error(message=str(exc))
