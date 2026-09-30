from __future__ import annotations

from typing import Any, Literal

import pipelex_tools
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from api.errors import raise_validation_error
from api.limits import MAX_MTHDS_FILE_BYTES

router = APIRouter(tags=["tools"])


class MthdsToolRequest(BaseModel):
    """Shared single-file request body for lightweight MTHDS editor tooling."""

    content: str = Field(..., description="Single .mthds file content to lint or format.")

    @field_validator("content")
    @classmethod
    def _bound_content(cls, value: str) -> str:
        if len(value.encode("utf-8")) > MAX_MTHDS_FILE_BYTES:
            msg = f"MTHDS file exceeds {MAX_MTHDS_FILE_BYTES // 1024} KiB limit"
            raise ValueError(msg)
        return value


class LintRequest(MthdsToolRequest):
    """Body of `POST /lint`."""

    source: str | None = Field(
        default=None,
        description=(
            "Optional logical filename for the content. Accepted for parity with `pipelex_tools.lint_mthds`; "
            "current diagnostics do not yet include the filename."
        ),
    )


class FormatRequest(MthdsToolRequest):
    """Body of `POST /format`."""

    options: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Optional formatter options passed through to `pipelex_tools.format_mthds`, such as "
            "`column_width`. Malformed option values return a 422 problem response."
        ),
    )


class Range(BaseModel):
    """Byte offsets plus 1-based line/column coordinates from `pipelex-tools-py`."""

    start_offset: int
    end_offset: int
    start_line: int
    start_col: int
    end_line: int
    end_col: int


class Diagnostic(BaseModel):
    """Structured lint/format diagnostic returned by `pipelex-tools-py`."""

    kind: Literal["syntax", "semantic", "schema"]
    severity: str
    message: str
    location: str | None
    range: Range | None


class LintResponse(BaseModel):
    """Response body of `POST /lint`."""

    diagnostics: list[Diagnostic]


class FormatResponse(BaseModel):
    """Response body of `POST /format`."""

    formatted: str
    changed: bool
    diagnostics: list[Diagnostic]


@router.post("/lint", response_model=LintResponse)
async def lint_mthds(request_data: LintRequest) -> LintResponse:
    """Lint one .mthds file with the embedded MTHDS schema.

    Malformed .mthds content is a produced diagnostic verdict and returns 200.
    Request-shape problems remain RFC 7807 422 responses through the global handlers.
    """
    result = pipelex_tools.lint_mthds(request_data.content, source=request_data.source)
    return LintResponse.model_validate(result)


@router.post("/format", response_model=FormatResponse)
async def format_mthds(request_data: FormatRequest) -> FormatResponse:
    """Format one .mthds file with the canonical MTHDS formatter.

    Syntax errors return 200 with diagnostics and unchanged content. Malformed
    formatter options are caller input errors and return RFC 7807 422.
    """
    try:
        result = pipelex_tools.format_mthds(request_data.content, options=request_data.options)
    except ValueError as exc:
        raise_validation_error(str(exc))
    return FormatResponse.model_validate(result)
