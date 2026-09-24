"""`extras` — the opaque labels a host attaches to a run.

**The runtime does not know what an organization is, and must not learn.** That
is the same rule `pipelex.system.storage_scope` states for where a run's bytes
go, and this module is its counterpart for everything else a host wants to say
about a run: a host that runs Pipelex for many tenants needs a run to carry the
host's own labels — which organization, which workspace — and Pipelex needs
somewhere to put labels it will forward without reading. `extras` is that
somewhere — an opaque, host-supplied mapping of string key to string value that
the runtime carries on `RunMetadata`, unread. The run model and the job
preparation signatures therefore name no host concept and no consumer: the
library never reads a key by name, and nothing here says what the labels are for.

**Where the labels go today.** Carrying the mapping unread is all this module
does, but it is read downstream: the telemetry layer writes a run's mapping onto
its spans as `pipelex.run.extras` and forwards it, whole, as the groups of each
PostHog capture — on the operator's stream and on Pipelex's own — because PostHog
is the backend that supports grouping. So whatever is put here is a live group
key in those projects and a span attribute on every OpenTelemetry export, and the
bounds below are shaped by that consumer.

The hosted Pipelex platform fills it with `{"organization": "<org_id>"}`, but
nothing here knows or checks that: no key is privileged, and a deployment that
sends `{"tenant": …, "workspace": …}` is served identically. A single-user
deployment sends nothing at all.

**Why the value is validated on the type.** The mapping is caller data that
arrives over a wire, so its contents are whatever the other side put there. It
is then quoted into log lines and forwarded to a telemetry backend, where a
newline is a log-forging primitive and an unbounded mapping is an unbounded
capture payload. Validating at construction — on `RunMetadata` and on the bridge
payload, through this one helper — means a malformed mapping is a decoding error
naming the field, at the edge, rather than a failure inside whichever capture
first tried to use it.

**Why an empty default is right here and was wrong for `storage_scope`.** An
absent label creates no shared namespace and misattributes nothing; it only
leaves the downstream group facet empty. The doctrine that made `user_id` and
`storage_scope` non-defaulting is about identity and about storage keys, and
both of those still refuse to default.
"""

from __future__ import annotations

import re

# An extras KEY: lowercase snake_case, starting with a letter.
#
# Deliberately narrower than the value charset. The key is forwarded as a group
# type, a schema-level name a telemetry backend registers once and then shows in
# a picker, so it is written by whoever integrates the host, not derived from
# tenant data — the tight shape costs an integrator nothing and keeps a stray id
# out of the facet list. Applied with `fullmatch` (see below).
RUN_EXTRAS_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# An extras VALUE: typically the identifier of one of the host's entities.
#
# This one IS tenant data — an org id, a workspace slug — so it admits both
# cases, digits, `_` and `-`, which covers every id shape the platform mints,
# and nothing else. No `/`, no `.`, no whitespace and no control character: the
# value is quoted into log lines and into capture payloads, and a newline in it
# is a log-forging primitive exactly as it is in a storage scope.
RUN_EXTRAS_VALUE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# How many entries one run's extras may carry.
#
# A bound is needed because the mapping is unbounded caller input crossing a
# wire and is attached to every span of a run. It lands at five because that is
# where the most constrained consumer sits — every entry is forwarded as a group
# type, and a telemetry backend typically registers a small fixed number of group
# types per project — so a sixth could not be honoured downstream anyway, and
# refusing it at the edge is more honest than forwarding a value that will be
# dropped in silence.
RUN_EXTRAS_MAX_ENTRIES = 5


def validate_run_extras(*, value: dict[str, str]) -> dict[str, str]:
    """Return `value` if it is a usable run-extras mapping, else raise `ValueError`.

    Args:
        value: The host-supplied mapping of opaque key to opaque value. An empty
            mapping is valid and means "the host attaches no labels to this run".

    Returns:
        The mapping, unchanged — this validator never normalizes, because the
        runtime does not own the vocabulary and lowercasing a tenant's id would
        silently address a different entity.

    Raises:
        ValueError: the mapping holds more than `RUN_EXTRAS_MAX_ENTRIES`
            entries, or a key or a value falls outside its charset — which
            covers the empty string, whitespace, control characters, and
            anything that could forge a line in a log or a capture payload.
    """
    if len(value) > RUN_EXTRAS_MAX_ENTRIES:
        msg = (
            f"Invalid extras: {len(value)} entries, at most {RUN_EXTRAS_MAX_ENTRIES} are accepted. "
            "Each entry is forwarded as one group type a telemetry backend registers for the project, and that "
            "budget is small and fixed — an entry beyond it could not be honoured downstream."
        )
        raise ValueError(msg)

    # `fullmatch`, NOT `match`. A trailing `$` in a `match` still admits one
    # final newline, which is how `storage_scope` once let a newline travel into
    # every storage key and log line built from it. The anchors below are
    # therefore redundant but kept: the patterns are also read on their own.
    for extras_key, extras_value in value.items():
        if not RUN_EXTRAS_KEY_PATTERN.fullmatch(extras_key):
            msg = (
                f"Invalid extras key {extras_key!r}: expected lowercase snake_case starting with a letter, "
                "at most 32 characters (e.g. 'organization'). A key is forwarded as a facet name registered with "
                "the telemetry backend, not tenant data."
            )
            raise ValueError(msg)
        if not RUN_EXTRAS_VALUE_PATTERN.fullmatch(extras_value):
            msg = (
                f"Invalid extras value {extras_value!r} for key {extras_key!r}: expected 1 to 128 characters "
                "from [A-Za-z0-9_-] (e.g. 'org_acme'). The value is quoted into log lines and capture payloads, "
                "so whitespace, control characters and separators are refused."
            )
            raise ValueError(msg)
    return value
