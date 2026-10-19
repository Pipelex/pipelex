"""Models endpoints — the MTHDS Protocol model deck this runner routes to, and the model reference check."""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from mthds.protocol.models import ModelCategory
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_reference import ModelReference
from pipelex.cogt.models.model_reference_check import ModelCheckCategory, ModelReferenceVerdict, check_model_reference
from pipelex.pipeline.runner import PipelexModelDeck
from pipelex.runtime_hub import get_model_deck

from pipelex_api.exceptions import RunnerRequestError
from pipelex_api.routes.pipelex.pipeline import ApiRunner

router = APIRouter(tags=["agent"])

# The longest reference the check accepts once trimmed; one character more is refused with `request.invalid`.
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
    and unknown categories are both 422 `request.invalid` naming `type`.
    """
    # Protocol arity: `type` is a plain single-value enum. FastAPI silently keeps one of
    # several repeated scalar query params, so the multi-value rejection must be explicit.
    if len(request.query_params.getlist("type")) > 1:
        msg = "The `type` query parameter accepts a single value"
        raise RunnerRequestError(msg, field="type")
    category: ModelCategory | None = None
    if model_type is not None:
        try:
            category = ModelCategory(model_type)
        except ValueError as exc:
            valid = ", ".join(sorted(member.value for member in ModelCategory))
            msg = f"Invalid model category. Valid values: {valid}"
            raise RunnerRequestError(msg, field="type") from exc
    return await ApiRunner().models(category=category)


# NOT tagged `x-mthds-protocol`: the check is a Pipelex API extension, and the flag marks the
# standard's own operations alone. Its refusals are the composite router's shared problem+json 422.
@router.get("/models/check")
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
) -> ModelReferenceVerdict:
    """Check whether one model reference resolves on this runner, as what, to which model (Pipelex API extension).

    Answers from pipelex's own reference parser and deck lookups, the ones a validation runs, so a
    reference found `resolved` in a category is one a pipe of that category may name, and one found
    `not_found` is one a validation refuses. A verdict is a `200` whatever the resolution, and on
    `not_found` it carries the suggestions a failing validation of the same reference offers. A
    request that cannot produce a verdict is an input `422` `request.invalid` naming the parameter: a
    missing or repeated `reference`, a repeated `type`, a reference that is blank, a sigil or a namespace
    alone, or too long, and an unknown `type`.
    """
    for parameter_name in ("reference", "type"):
        if len(request.query_params.getlist(parameter_name)) > 1:
            msg = f"The `{parameter_name}` query parameter accepts a single value"
            raise RunnerRequestError(msg, field=parameter_name)

    # The parser trims the reference itself, and its `raw` is the trimmed text the length limit measures.
    try:
        parsed_reference = ModelReference.parse(reference)
    except ModelReferenceParseError as exc:
        raise RunnerRequestError(exc.message, field="reference") from exc
    if len(parsed_reference.raw) > MAX_MODEL_REFERENCE_LENGTH:
        too_long_message = (
            f"The model reference holds {len(parsed_reference.raw)} characters once trimmed, more than the {MAX_MODEL_REFERENCE_LENGTH} accepted"
        )
        raise RunnerRequestError(too_long_message, field="reference")

    category: ModelCheckCategory | None = None
    if model_type is not None:
        try:
            category = ModelCheckCategory(model_type)
        except ValueError as exc:
            valid = ", ".join(sorted(member.value for member in ModelCheckCategory))
            msg = f"Invalid model category. Valid values: {valid}"
            raise RunnerRequestError(msg, field="type") from exc

    return check_model_reference(model_deck=get_model_deck(), reference=parsed_reference, category=category)
