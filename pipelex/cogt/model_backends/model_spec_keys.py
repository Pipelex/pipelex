"""Sorting a per-model backend table into blueprint fields, request headers, and everything else.

`InferenceModelSpecBlueprint` is strict, so a per-model key it does not know cannot simply be validated
away. Historically every such key was moved to `extra_headers` and sent to the provider as a request
header — which is right for `x-portkey-config` and wrong for a typo or a field deleted from the blueprint,
both of which then went out on the wire while the real setting stayed unset.

The rule here is a shape rule, not a name allowlist, so the served gateway config can start carrying a
new `x-portkey-*` header without waiting for a client release: **an unknown key is a header only if it
contains a hyphen.** Header names conventionally do; blueprint field names never do, because they are
Python identifiers. A hyphenated spelling of a known field (`max-tokens`) is the one hole that leaves,
and it is closed by name.

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


class RejectedModelSpecKey(NamedTuple):
    key: str
    near_miss_of: str | None
    """The known blueprint field this header-shaped key is a hyphenated spelling of, if any."""

    def describe(self) -> str:
        """The per-key reason; `describe_rejected_keys` adds the rule once for the whole list."""
        if self.near_miss_of is not None:
            return f"'{self.key}' looks like the model-spec field '{self.near_miss_of}' spelled with hyphens — use '{self.near_miss_of}'"
        return f"'{self.key}' is not a known model-spec field, and not header-shaped"


class ModelSpecKeySplit(NamedTuple):
    fields: dict[str, Any]
    headers: dict[str, str]
    rejected: list[RejectedModelSpecKey]


def describe_rejected_keys(*, rejected: list[RejectedModelSpecKey]) -> str:
    """The reasons for every rejected key, then the rule once, phrased for the person who has to fix the file."""
    reasons = "; ".join(rejected_key.describe() for rejected_key in rejected)
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
            rejected.append(RejectedModelSpecKey(key=key, near_miss_of=None))
            continue
        underscored = key.replace("-", "_")
        if underscored in known_fields:
            rejected.append(RejectedModelSpecKey(key=key, near_miss_of=underscored))
            continue
        headers[key] = value
    return ModelSpecKeySplit(fields=fields, headers=headers, rejected=rejected)
