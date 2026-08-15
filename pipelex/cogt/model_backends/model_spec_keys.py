"""Sorting a per-model backend table into blueprint fields, request headers, and everything else.

`InferenceModelSpecBlueprint` is strict, so a per-model key it does not know cannot simply be validated
away. Historically every such key was moved to `extra_headers` and sent to the provider as a request
header — which is right for `x-portkey-config` and wrong for a typo or a field deleted from the blueprint,
both of which then went out on the wire while the real setting stayed unset.

The rule here is a shape rule, not a name allowlist, so the served gateway config can start carrying a
new `x-portkey-*` header without waiting for a client release: **an unknown key is a header only if it
contains a hyphen and its value is a string.** Header names conventionally do; blueprint field names
never do, because they are Python identifiers. A hyphenated spelling of a known field (`max-tokens`) is
the one hole that leaves, and it is closed by name. The value half is not coercion: `x-foo = 3` is an
unquoted value, and `str(True)` or `str(["a"])` on the wire is exactly the rogue header this guards
against, so a non-string value is rejected rather than stringified.

This module is deliberately pure and deliberately silent. It runs on the success path of every backend
load, including loads that precede `runtime_hub.set_config()`, so a `log` call here would turn a data
transform into a boot-order dependency. It also does not decide what a rejected key *means*: only the
caller knows whether the table came from a local file (where a rejected key is the author's typo, and
fatal) or from the served gateway config (where it is version skew, and pruned).
"""

from enum import StrEnum
from typing import Any, NamedTuple

from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint

HEADER_KEY_EXAMPLE = "x-portkey-provider"


class ModelSpecSource(StrEnum):
    """Where a per-model table was read from — the only thing that decides what a rejected key means."""

    LOCAL_FILE = "local_file"
    REMOTE_GATEWAY = "remote_gateway"


class ModelSpecKeyRejection(StrEnum):
    """Why an unknown per-model key was not accepted as a request header."""

    NOT_HEADER_SHAPED = "not_header_shaped"
    HYPHENATED_KNOWN_FIELD = "hyphenated_known_field"
    NON_STRING_VALUE = "non_string_value"

    @property
    def is_about_shape(self) -> bool:
        """Whether the hyphen rule is the advice to give — a non-string value already has one."""
        match self:
            case ModelSpecKeyRejection.NOT_HEADER_SHAPED | ModelSpecKeyRejection.HYPHENATED_KNOWN_FIELD:
                return True
            case ModelSpecKeyRejection.NON_STRING_VALUE:
                return False


class RejectedModelSpecKey(NamedTuple):
    key: str
    reason: ModelSpecKeyRejection
    near_miss_of: str | None = None
    """The known blueprint field this header-shaped key is a hyphenated spelling of — set for `HYPHENATED_KNOWN_FIELD` only."""

    def describe(self) -> str:
        """The per-key reason; `describe_rejected_keys` adds the hyphen rule once for the whole list when it applies."""
        match self.reason:
            case ModelSpecKeyRejection.NOT_HEADER_SHAPED:
                return f"'{self.key}' is not a known model-spec field, and not header-shaped"
            case ModelSpecKeyRejection.HYPHENATED_KNOWN_FIELD:
                return f"'{self.key}' looks like the model-spec field '{self.near_miss_of}' spelled with hyphens — use '{self.near_miss_of}'"
            case ModelSpecKeyRejection.NON_STRING_VALUE:
                return f"'{self.key}' is header-shaped, but its value is not a string — a request header value must be a quoted string"


class ModelSpecKeySplit(NamedTuple):
    fields: dict[str, Any]
    headers: dict[str, str]
    rejected: list[RejectedModelSpecKey]


def describe_rejected_keys(*, rejected: list[RejectedModelSpecKey]) -> str:
    """The reasons for every rejected key, then the hyphen rule once if any key broke it, phrased for the person who has to fix the file."""
    reasons = "; ".join(rejected_key.describe() for rejected_key in rejected)
    if not any(rejected_key.reason.is_about_shape for rejected_key in rejected):
        return f"{reasons}."
    return (
        f"{reasons}. A per-model key that is not a model-spec field is sent to the provider as a request header "
        f"and must contain a hyphen (e.g. '{HEADER_KEY_EXAMPLE}'): fix the typo, or name the key like a header if that is what it is meant to be."
    )


def is_header_shaped(*, key: str) -> bool:
    return "-" in key


def split_model_spec_keys(*, model_spec_dict: dict[str, Any]) -> ModelSpecKeySplit:
    """Split one per-model table into blueprint fields, request headers, and rejected keys.

    Order is preserved throughout, and the input is not modified.
    """
    known_fields = InferenceModelSpecBlueprint.model_fields.keys()
    fields: dict[str, Any] = {}
    headers: dict[str, str] = {}
    rejected: list[RejectedModelSpecKey] = []
    for key, value in model_spec_dict.items():
        if key in known_fields:
            fields[key] = value
            continue
        if not is_header_shaped(key=key):
            rejected.append(RejectedModelSpecKey(key=key, reason=ModelSpecKeyRejection.NOT_HEADER_SHAPED))
            continue
        underscored = key.replace("-", "_")
        if underscored in known_fields:
            rejected.append(RejectedModelSpecKey(key=key, reason=ModelSpecKeyRejection.HYPHENATED_KNOWN_FIELD, near_miss_of=underscored))
            continue
        if not isinstance(value, str):
            rejected.append(RejectedModelSpecKey(key=key, reason=ModelSpecKeyRejection.NON_STRING_VALUE))
            continue
        headers[key] = value
    return ModelSpecKeySplit(fields=fields, headers=headers, rejected=rejected)
