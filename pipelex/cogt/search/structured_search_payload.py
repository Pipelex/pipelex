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
exactly ``data`` and ``sources`` **and** the caller's own output structure does not declare those two
names itself — that last clause is what stops a legitimate ``{data, sources}`` output class from being
unwrapped into its own sub-object.
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

    Field names *and* aliases are checked because the response is keyed by the schema's property names,
    which pydantic emits by alias — so an output structure that reaches the wire as ``{data, sources}``
    must be recognised as its own payload whichever way it spells those fields in Python.
    """
    if frozenset(payload) != _ENVELOPE_KEYS:
        return False
    declared = set(schema.model_fields)
    declared.update(field.alias for field in schema.model_fields.values() if field.alias)
    return not _ENVELOPE_KEYS.issubset(declared)
