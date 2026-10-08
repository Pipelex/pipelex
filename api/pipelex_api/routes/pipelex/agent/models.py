"""Models endpoints — the MTHDS Protocol model deck this runner routes to, and the model reference check."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from mthds.protocol.models import ModelCategory
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.cogt.models.model_reference_check import ModelCheckCategory, ModelReferenceVerdict, check_model_reference
from pipelex.pipeline.runner import PipelexModelDeck
from pipelex.runtime_hub import get_model_deck

from pipelex_api.error_types import ErrorType
from pipelex_api.errors import raise_validation_error
from pipelex_api.routes.pipelex.pipeline import ApiRunner

router = APIRouter(tags=["agent"])

# The longest reference the check accepts once trimmed; one character more is refused with `InvalidModelReference`.
MAX_MODEL_REFERENCE_LENGTH = 199


@router.get("/models", openapi_extra={"x-mthds-protocol": True})
async def get_models(
    request: Request,
    model_type: Annotated[
        str | None,
        Query(alias="type", description="Filter by model category: llm, extract, img_gen, search, judgment. Single value (protocol arity)."),
    ] = None,
) -> PipelexModelDeck:
    """List the model deck this runner can route to (MTHDS Protocol `GET /models`).

    Answers the protocol `ModelDeck` as produced by `PipelexMTHDSProtocol.models` —
    the flat `models` list (`{name, type}` entries) plus this implementation's
    category-keyed routing extensions (`aliases`, `waterfalls`). The `type` query
    param is a SINGLE protocol `ModelCategory` value: repeated `?type=` values
    (arity, `ValidationError`) and unknown categories (`InvalidModelCategory`) are
    both 422s (RFC 7807).
    """
    # Protocol arity: `type` is a plain single-value enum. FastAPI silently keeps one of
    # several repeated scalar query params, so the multi-value rejection must be explicit.
    # Generic ValidationError, not InvalidModelCategory: the values may all be valid —
    # what's wrong is the arity.
    if len(request.query_params.getlist("type")) > 1:
        raise_validation_error(message="The `type` query parameter accepts a single value")
    category: ModelCategory | None = None
    if model_type is not None:
        try:
            category = ModelCategory(model_type)
        except ValueError:
            valid = ", ".join(sorted(member.value for member in ModelCategory))
            raise_validation_error(
                message=f"Invalid model category. Valid values: {valid}",
                error_type=ErrorType.INVALID_MODEL_CATEGORY,
            )
    return await ApiRunner().models(category=category)


@router.get(
    "/models/check",
    response_model=ModelReferenceVerdict,
    # NOT tagged `x-mthds-protocol`: the check is a Pipelex API extension, and the flag marks the
    # standard's five operations alone. Its refusals are the composite router's shared problem+json 422.
)
async def check_model(
    request: Request,
    reference: Annotated[
        str,
        Query(
            description=(
                "The model reference as a method's `model` field writes it: `$preset`, `@alias`, `~waterfall`, a bare model handle, "
                "or one of the namespaces `preset:`, `alias:`, `waterfall:` and `handle:`. Surrounding whitespace is ignored, "
                f"and the trimmed reference holds at most {MAX_MODEL_REFERENCE_LENGTH} characters. Single value."
            ),
        ),
    ],
    model_type: Annotated[
        str | None,
        Query(
            alias="type",
            description=(
                "The category to check in: llm, extract, img_gen, search, judgment or doc_gen. "
                "When absent, the check is made in every one of them. Single value."
            ),
        ),
    ] = None,
) -> JSONResponse:
    """Check whether one model reference resolves on this runner, as what, to which model (Pipelex API extension).

    Answers from pipelex's own reference parser and deck lookups, the ones a validation runs, so a
    reference found `resolved` in a category is one a pipe of that category may name, and one found
    `not_found` is one a validation refuses. A verdict is a `200` whatever the resolution, and on
    `not_found` it carries the suggestions a failing validation of the same reference offers. A
    request that cannot produce a verdict is an input `422`: `ValidationError` for a missing or
    repeated `reference` or a repeated `type`, `InvalidModelReference` for a reference that is blank,
    a sigil or a namespace alone, or too long, and `InvalidModelCategory` for an unknown `type`.
    """
    for parameter_name in ("reference", "type"):
        if len(request.query_params.getlist(parameter_name)) > 1:
            raise_validation_error(message=f"The `{parameter_name}` query parameter accepts a single value")

    trimmed_reference = reference.strip()
    if len(trimmed_reference) > MAX_MODEL_REFERENCE_LENGTH:
        too_long_message = (
            f"The model reference holds {len(trimmed_reference)} characters once trimmed, more than the {MAX_MODEL_REFERENCE_LENGTH} accepted"
        )
        raise_validation_error(message=too_long_message, error_type=ErrorType.INVALID_MODEL_REFERENCE)
    try:
        parsed_reference = ModelReference.parse(trimmed_reference)
    except ModelReferenceParseError as exc:
        raise_validation_error(message=exc.message, error_type=ErrorType.INVALID_MODEL_REFERENCE)

    category: ModelCheckCategory | None = None
    if model_type is not None:
        try:
            category = ModelCheckCategory(model_type)
        except ValueError:
            valid = ", ".join(sorted(member.value for member in ModelCheckCategory))
            raise_validation_error(
                message=f"Invalid model category. Valid values: {valid}",
                error_type=ErrorType.INVALID_MODEL_CATEGORY,
            )

    verdict = check_model_reference(model_deck=get_model_deck(), reference=parsed_reference, category=category)
    return JSONResponse(content=verdict.model_dump(mode="json"))
