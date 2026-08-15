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

Shaped like a header is not the same as usable as one, so a second gate follows the first: the name
must be an RFC 7230 token, and the value must be printable ASCII on a single line with no leading or
trailing whitespace. Both are what the HTTP stack itself enforces — a quoted key like `x-foo bar`, or
a value carrying a CR/LF or an invisible trailing space, is refused by h11 when the request is built,
so without this gate the author hears about the mistake on the first inference call instead of at
boot. One deliberate divergence: h11 accepts `0x7f` (DEL) in a value and this does not, because a DEL
in a config file is never intentional and "printable ASCII" is a rule a reader can hold in their head.
Nothing here couples to h11's own patterns — it is a transitive dependency of httpx, and the rule must
not become "whatever this version of h11 does".

This module is deliberately pure and deliberately silent. It runs on the success path of every backend
load, including loads that precede `runtime_hub.set_config()`, so a `log` call here would turn a data
transform into a boot-order dependency. It also does not decide what a rejected key *means*: only the
caller knows whether the table came from a local file (where a rejected key is the author's typo, and
fatal) or from the served gateway config (where it is version skew, and pruned).
"""

import re
from enum import StrEnum
from typing import Any, NamedTuple

from pipelex.cogt.model_backends.model_spec_factory import InferenceModelSpecBlueprint

HEADER_KEY_EXAMPLE = "x-portkey-provider"
HEADER_NAME_CHARACTERS = "letters, digits and the characters !#$%&'*+-.^_`|~"

# An RFC 7230 header field name is a token, and a field value is printable ASCII on a single line.
_HEADER_NAME_PATTERN = re.compile(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+")
_HEADER_VALUE_PATTERN = re.compile(r"([\x21-\x7e]([ \t\x21-\x7e]*[\x21-\x7e])?)?")


class ModelSpecSource(StrEnum):
    """Where a per-model table was read from — the only thing that decides what a rejected key means."""

    LOCAL_FILE = "local_file"
    REMOTE_GATEWAY = "remote_gateway"


class ModelSpecKeyRejection(StrEnum):
    """Why an unknown per-model key was not accepted as a request header."""

    NOT_HEADER_SHAPED = "not_header_shaped"
    HYPHENATED_KNOWN_FIELD = "hyphenated_known_field"
    ILLEGAL_HEADER_NAME = "illegal_header_name"
    NON_STRING_VALUE = "non_string_value"
    ILLEGAL_HEADER_VALUE = "illegal_header_value"


class RejectedModelSpecKey(NamedTuple):
    key: str
    reason: ModelSpecKeyRejection
    near_miss_of: str | None = None
    """The known blueprint field this header-shaped key is a hyphenated spelling of — set for `HYPHENATED_KNOWN_FIELD` only."""
    illegal_character: str | None = None
    """The first character barring this key from being a header field name — set for `ILLEGAL_HEADER_NAME` only."""

    def describe(self) -> str:
        """The per-key reason; `describe_rejected_keys` adds the hyphen rule once for the whole list when it applies."""
        match self.reason:
            case ModelSpecKeyRejection.NOT_HEADER_SHAPED:
                return f"'{self.key}' is not a known model-spec field, and not header-shaped"
            case ModelSpecKeyRejection.HYPHENATED_KNOWN_FIELD:
                return f"'{self.key}' looks like the model-spec field '{self.near_miss_of}' spelled with hyphens — use '{self.near_miss_of}'"
            case ModelSpecKeyRejection.ILLEGAL_HEADER_NAME:
                return (
                    f"'{self.key}' cannot be a header name: {self.illegal_character!r} is not allowed in one — "
                    f"a header name may contain only {HEADER_NAME_CHARACTERS}"
                )
            case ModelSpecKeyRejection.NON_STRING_VALUE:
                return f"'{self.key}' is header-shaped, but its value is not a string — a request header value must be a quoted string"
            case ModelSpecKeyRejection.ILLEGAL_HEADER_VALUE:
                return (
                    f"'{self.key}' is header-shaped, but its value cannot be sent as a header value — it must be printable ASCII "
                    "on a single line, with no leading or trailing whitespace"
                )


class ModelSpecKeySplit(NamedTuple):
    fields: dict[str, Any]
    headers: dict[str, str]
    rejected: list[RejectedModelSpecKey]


def describe_rejected_keys(*, rejected: list[RejectedModelSpecKey]) -> str:
    """The reasons for every rejected key, then the hyphen rule once if any key lacked one, phrased for the person who has to fix the file.

    Only a `NOT_HEADER_SHAPED` key earns the trailer: every other rejection already has a hyphen and is told what is
    actually wrong with it — the field it resembles, the illegal character, the unquoted value — so "add a hyphen"
    would be wrong advice.
    """
    reasons = "; ".join(rejected_key.describe() for rejected_key in rejected)
    if not any(rejected_key.reason is ModelSpecKeyRejection.NOT_HEADER_SHAPED for rejected_key in rejected):
        return f"{reasons}."
    return (
        f"{reasons}. A per-model key that is not a model-spec field is sent to the provider as a request header "
        f"and must contain a hyphen (e.g. '{HEADER_KEY_EXAMPLE}'): fix the typo, or name the key like a header if that is what it is meant to be."
    )


def is_header_shaped(*, key: str) -> bool:
    """Whether the author meant this key as a header at all: a blueprint field name is an identifier and never carries a hyphen."""
    return "-" in key


def is_legal_header_name(*, key: str) -> bool:
    """Whether the wire will carry this key as a header field name."""
    return _HEADER_NAME_PATTERN.fullmatch(key) is not None


def first_illegal_header_name_character(*, key: str) -> str | None:
    """The first character barring this key from being a header field name, so the error can name it."""
    for character in key:
        if _HEADER_NAME_PATTERN.fullmatch(character) is None:
            return character
    return None


def is_legal_header_value(*, value: str) -> bool:
    """Whether the wire will carry this string as a header field value."""
    return _HEADER_VALUE_PATTERN.fullmatch(value) is not None


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
        if not is_legal_header_name(key=key):
            rejected.append(
                RejectedModelSpecKey(
                    key=key,
                    reason=ModelSpecKeyRejection.ILLEGAL_HEADER_NAME,
                    illegal_character=first_illegal_header_name_character(key=key),
                )
            )
            continue
        if not isinstance(value, str):
            rejected.append(RejectedModelSpecKey(key=key, reason=ModelSpecKeyRejection.NON_STRING_VALUE))
            continue
        if not is_legal_header_value(value=value):
            rejected.append(RejectedModelSpecKey(key=key, reason=ModelSpecKeyRejection.ILLEGAL_HEADER_VALUE))
            continue
        headers[key] = value
    return ModelSpecKeySplit(fields=fields, headers=headers, rejected=rejected)
