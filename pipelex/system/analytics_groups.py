"""`analytics_groups` — the opaque group labels a host attaches to a run.

**The runtime does not know what an organization is, and must not learn.** That
is the same rule `pipelex.system.storage_scope` states for where a run's bytes
go, and this module is its telemetry counterpart: a host that runs Pipelex for
many tenants needs a run's spans and events to belong to the entities that
tenant cares about, and Pipelex needs somewhere to put labels it will forward
without reading. `analytics_groups` is that somewhere — an opaque, host-supplied
mapping of group *type* to group *key* that the runtime carries on
`RunMetadata`, unread, for a telemetry consumer that understands groups to
forward. Carrying it unread is all this module does, but it is read downstream:
a run's mapping rides its spans as `pipelex.run.analytics_groups` and becomes
PostHog's own groups facet on the operator's stream, so whatever is put here is
a live group key in that project and a span attribute on every OpenTelemetry
export. Pipelex's own stream is the exception — one shared project across every
deployment, where a host's group vocabulary would collide with another's, so
the mapping never reaches it.

The hosted Pipelex platform fills it with `{"organization": "<org_id>"}`, but
nothing here knows or checks that: no key is privileged, and a deployment that
sends `{"tenant": …, "plan_tier": …}` is served identically. A single-user
deployment sends nothing at all.

**Why it carries groups and not free properties.** A telemetry backend gives an
event two different destinations. A *group* is an entity the event belongs to,
and it is what makes entity-level counts, funnels and retention possible after
the fact; a *property* is a free scalar on the event and can do none of that. A
generic extras bag would force the runtime to sort entries between the two, and
since it may not read a key by name it would have to send everything one way —
spending a backend's scarce group-type budget on values like a plan tier, or
losing entity analytics entirely. So the facet is named in the field. If a host
ever needs free properties on a run, that is a sibling field routed by facet,
and this one keeps its name and its meaning.

**Why the value is validated on the type.** The mapping is caller data that
arrives over a wire, so its contents are whatever the other side put there. It
is then quoted into log lines and forwarded to a telemetry backend, where a
newline is a log-forging primitive and an unbounded mapping is an unbounded
capture payload. Validating at construction — on `RunMetadata` and on the bridge
payload, through this one helper — means a malformed mapping is a decoding error
naming the field, at the edge, rather than a failure inside whichever capture
first tried to use it.

**Why an empty default is right here and was wrong for `storage_scope`.** An
absent group creates no shared namespace and misattributes nothing; it only
leaves the group facet empty. The doctrine that made `user_id` and
`storage_scope` non-defaulting is about identity and about storage keys, and
both of those still refuse to default.
"""

from __future__ import annotations

import re

# A group TYPE: the facet name, lowercase snake_case, starting with a letter.
#
# Deliberately narrower than the value charset. A group type is a schema-level
# name that a telemetry backend registers once and then shows in a picker, so it
# is written by whoever integrates the host, not derived from tenant data — the
# tight shape costs an integrator nothing and keeps a stray id out of the facet
# list. Applied with `fullmatch` (see below).
ANALYTICS_GROUP_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# A group KEY: the identifier of one entity inside a type.
#
# This one IS tenant data — an org id, a workspace slug — so it admits both
# cases, digits, `_` and `-`, which covers every id shape the platform mints,
# and nothing else. No `/`, no `.`, no whitespace and no control character: the
# value is quoted into log lines and into capture payloads, and a newline in it
# is a log-forging primitive exactly as it is in a storage scope.
ANALYTICS_GROUP_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# How many group types one run may carry.
#
# A bound is needed because the mapping is unbounded caller input crossing a
# wire and is attached to every span of a run. It lands at five because that is
# where the most constrained consumer of the group facet sits — a telemetry
# backend typically registers a small fixed number of group types per project —
# so a sixth could not be honoured downstream anyway, and refusing it at the
# edge is more honest than forwarding a value that will be dropped in silence.
ANALYTICS_GROUPS_MAX_ENTRIES = 5


def validate_analytics_groups(*, value: dict[str, str]) -> dict[str, str]:
    """Return `value` if it is a usable analytics-groups mapping, else raise `ValueError`.

    Args:
        value: The host-supplied mapping of group type to group key. An empty
            mapping is valid and means "this run belongs to no group".

    Returns:
        The mapping, unchanged — this validator never normalizes, because the
        runtime does not own the vocabulary and lowercasing a tenant's id would
        silently address a different entity.

    Raises:
        ValueError: the mapping holds more than `ANALYTICS_GROUPS_MAX_ENTRIES`
            entries, or a key or a value falls outside its charset — which
            covers the empty string, whitespace, control characters, and
            anything that could forge a line in a log or a capture payload.
    """
    if len(value) > ANALYTICS_GROUPS_MAX_ENTRIES:
        msg = (
            f"Invalid analytics_groups: {len(value)} entries, at most {ANALYTICS_GROUPS_MAX_ENTRIES} are accepted. "
            "Each entry is one group type a telemetry backend registers for the project, and that budget is "
            "small and fixed — an entry beyond it could not be honoured downstream."
        )
        raise ValueError(msg)

    # `fullmatch`, NOT `match`. A trailing `$` in a `match` still admits one
    # final newline, which is how `storage_scope` once let a newline travel into
    # every storage key and log line built from it. The anchors below are
    # therefore redundant but kept: the patterns are also read on their own.
    for group_type, group_key in value.items():
        if not ANALYTICS_GROUP_TYPE_PATTERN.fullmatch(group_type):
            msg = (
                f"Invalid analytics_groups group type {group_type!r} (a key of the mapping): expected lowercase "
                "snake_case starting with a letter, at most 32 characters (e.g. 'organization'). A group type is a "
                "facet name registered with the telemetry backend, not tenant data."
            )
            raise ValueError(msg)
        if not ANALYTICS_GROUP_KEY_PATTERN.fullmatch(group_key):
            msg = (
                f"Invalid analytics_groups group key {group_key!r} for group type {group_type!r} (a value of the "
                "mapping): expected 1 to 128 characters from [A-Za-z0-9_-] (e.g. 'org_acme'). The group key is "
                "quoted into log lines and capture payloads, so whitespace, control characters and separators "
                "are refused."
            )
            raise ValueError(msg)
    return value
