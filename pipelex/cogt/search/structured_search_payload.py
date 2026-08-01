"""Extract the payload a structured search owes its leaf, whatever envelope it arrived in.

A structured search's contract is the structured payload alone: the leaf validates it against the
caller's output structure class, which has nowhere to put sources. But Linkup answers a structured
search *with* sources as a ``{data, sources}`` envelope, and whether the envelope arrives is a
provider-side flag — set directly on the direct backend, set by the relay on the gateway backend.

Neither backend can therefore assume its own request shape decided the response shape:

- the direct backend asks for ``include_sources=False`` and expects the bare payload, but a provider
  that ignores the flag would hand back the envelope, and validating an envelope against an output
  class whose fields all have defaults succeeds *silently* — pydantic's default ``extra="ignore"``
  drops ``data`` and ``sources`` and returns an all-defaults object. Silent wrong answers, no error;
- the gateway backend's relay asks for sources today and so returns the envelope, but the moment it
  stops, a worker that demands the envelope rejects every search — a two-sided deploy hazard.

Recognising the envelope *structurally* removes both. A response is the envelope only when it carries
exactly ``data`` and ``sources`` **and** the caller's own output structure does not put those two names
on the wire itself — that last clause is what stops a legitimate ``{data, sources}`` output class from
being unwrapped into its own sub-object.
"""

from typing import Any, cast

from pydantic import BaseModel

_ENVELOPE_KEYS = frozenset({"data", "sources"})


def extract_structured_search_payload(*, response: Any, schema: type[BaseModel]) -> dict[str, Any] | None:
    """Return the structured payload to hand the leaf, or ``None`` when the response carries none.

    ``None`` covers two cases the caller can still tell apart from ``response`` itself, because they
    deserve different advice: a response that is not a JSON object at all (malformed — the model is the
    suspect), and an envelope whose ``data`` is null or not an object (the search simply found nothing
    to fill the output structure with — the query is the suspect).
    """
    if not isinstance(response, dict):
        return None
    payload = cast("dict[str, Any]", response)
    if not _is_sources_envelope(payload=payload, schema=schema):
        return payload
    data = payload["data"]
    if not isinstance(data, dict):
        return None
    return cast("dict[str, Any]", data)


def _is_sources_envelope(*, payload: dict[str, Any], schema: type[BaseModel]) -> bool:
    """Whether this object is Linkup's sources envelope rather than the structured payload itself.

    The declared names come from the generated JSON schema rather than from ``model_fields``, because the
    schema is what the provider was handed and the response is keyed by its property names. Pydantic emits
    those properties *by alias*, and only the schema knows which of a field's alias forms actually reaches
    the wire: ``Field(validation_alias=...)`` renames the property while leaving ``field.alias`` ``None``,
    whereas ``Field(serialization_alias=...)`` does not rename it at all. Reading the schema keeps this
    guard aligned with the provider by construction, instead of re-deriving pydantic's alias precedence
    here. It is reached only once the payload carries exactly the two envelope keys, so the schema build
    costs nothing on the ordinary path.
    """
    if frozenset(payload) != _ENVELOPE_KEYS:
        return False
    return not _ENVELOPE_KEYS.issubset(_declared_wire_names(schema=schema))


def _declared_wire_names(*, schema: type[BaseModel]) -> set[str]:
    """The property names the caller's output structure puts on the wire.

    A schema whose root is a ``$ref`` — what pydantic emits for a self-referencing model — carries its
    properties under ``$defs`` rather than at the top level, so the reference is followed before reading
    them; otherwise such a class would declare nothing and have its own payload unwrapped.
    """
    json_schema = schema.model_json_schema()
    root_ref = json_schema.get("$ref")
    if isinstance(root_ref, str):
        definitions = cast("dict[str, Any]", json_schema.get("$defs", {}))
        json_schema = cast("dict[str, Any]", definitions.get(root_ref.rsplit("/", 1)[-1], {}))
    return set(cast("dict[str, Any]", json_schema.get("properties", {})))
