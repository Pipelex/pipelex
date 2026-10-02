"""`storage_scope` — the one opaque string that decides where a run's bytes go.

**The runtime does not know what an organization or a method is, and must not
learn.** A host that runs Pipelex for many tenants needs every object a run
writes to land inside that tenant's namespace; Pipelex needs to compose leaves
(`assets/`, `results/`, `payloads/`) onto *something*. `storage_scope` is that
something: an opaque, host-supplied prefix that the runtime treats as a unit.

The hosted Pipelex platform fills it with `<org_id>/<method_id>/<run_id>`, but
nothing here knows or checks that — a single-user deployment can pass
`<user_id>/<run_id>` and a local one passes just `<run_id>`. Threading the
host's own concepts through the transport instead was considered and rejected:
`method_id` is a hosted catalog concept with no meaning in a source-available
runtime, and `uri_format`'s placeholder set is closed by design.

**Why the validation is here rather than at the call sites.** The value reaches
`StorageProviderAbstract.store()` as a key prefix, so a `..` or a leading slash
in it is a path traversal into another tenant's namespace. The Temporal payload
codec used to run a per-segment sanitizer over `user_id` and `pipeline_run_id`
separately; collapsing them into one slash-bearing string makes that sanitizer
unusable, and without an explicit validator here that change would silently
delete an existing traversal control. So the constraint moved to the type: a
`JobMetadata` cannot be constructed with a scope that is not path-safe, which
makes every downstream key safe by construction rather than by remembering.

**`read_scope` — the second opaque string, deciding what a run may read.** The
storage scope says where a run's bytes go; it says nothing about what the run
may read, and a value can carry any URL a method chose: a `pipelex-storage://`
key the storage provider reads with the process's bucket-wide credentials, or a
path it reads from the worker's own disk. On a multi-tenant host that is a read
of another tenant's file. So the host supplies a second prefix, the read scope:
every storage key the run reads must lie under it, and the run reads nothing
from the local disk. The hosted platform passes the organization id, which
covers the organization's uploads and the outputs of its earlier runs, both
outside the current run's storage scope; a run without a read scope (a laptop, a
single-tenant server) reads as it always did. The check itself lives in
`pipelex.tools.uri.uri_read_scope`.

It is a separate value supplied by the host, not a parse of the storage scope.
Taking the first segment of `<org_id>/<method_id>/<run_id>` would teach the
runtime the hosted layout this module exists to keep out, and it would be wrong
everywhere else: a local run's storage scope is its run id, which would confine
it to its own files.
"""

from __future__ import annotations

import re

# One to three `[A-Za-z0-9_-]` segments joined by single slashes.
#
# Applied with `fullmatch` (see below), it rejects in one rule: the empty string,
# a leading or trailing slash, an empty
# interior segment (`a//b`), `.` and `..` in any position, and any character
# that could re-open a traversal or a query string once the value is pasted into
# a URI. The upper bound of three segments is not cosmetic — it is what keeps a
# scope from swallowing the leaf (`assets/`, `results/`, `payloads/`) that the
# runtime appends to it.
STORAGE_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){0,2}$")

# The scope for a run that provably never stores anything: a dry run.
#
# Dry runs construct a `JobMetadata` without a real run behind them, so they
# need a value for a required field. An explicit, greppable constant is used
# rather than an empty string or a `None` default, because a silent default on
# THIS field is exactly how the `anonymous/` namespace grew the first time — a
# placeholder that was never meant to reach storage became the key prefix for
# every unauthenticated run. If this value ever shows up as an S3 key prefix,
# something stored during a dry run and that is the bug to chase.
DRY_RUN_STORAGE_SCOPE = "dry-run-no-storage"

# The caller a dry run is attributed to.
#
# It used to be `OTelConstants.DEFAULT_USER_ID` — the string "anonymous", which
# is a TELEMETRY placeholder meaning "a span with no known caller". Reusing it
# as an *identity* is how that string reached the storage path in the first
# place, and the whole point of this module is that it must not. A dry run has
# no caller in the identity sense either, so it says so in its own word instead
# of borrowing telemetry's.
DRY_RUN_USER_ID = "dry-run-no-user"

# The identity and scope of a run on somebody's own machine.
#
# These are DEFAULTS ON A CONSTRUCTOR, which is a different thing from the
# `or DEFAULT_USER_ID` fallback they replace, and the difference is the whole
# point. A local run genuinely has one user and no tenancy, so "local" is a true
# statement made once, at the boundary where it is true. The old fallback sat
# deep in `pipeline_run_setup`, where it turned a *missing* identity on a
# multi-tenant server into a present-looking one and pointed every such run at
# one shared namespace.
#
# So: a host that serves more than one tenant must pass its own values. It
# cannot reach these by omission — the seam it calls, `pipeline_run_setup`,
# requires both explicitly.
#
# `LOCAL_STORAGE_SCOPE` is a SENTINEL and never reaches a storage key.
# `pipeline_run_setup` swaps it for the run id the moment that id exists, so a
# local run is scoped `<run_id>`, not `local/<run_id>`. A tenancy segment on a
# laptop separates nothing — there is exactly one tenant — while the run id is
# the only thing that has to be distinct, because anything stored under a fixed
# name (`results/main_stuff.json`) would otherwise be overwritten by the next
# run. `LOCAL_USER_ID` is not a sentinel either: it is an identity, it is true,
# and it is carried and stored as-is. Telemetry is the one place that declines
# it — it is the same string on every machine, so honouring it as a person would
# collapse every Pipelex user's local runs onto one, and both PostHog streams
# report under their own fallback instead. See
# `_NON_DISTINGUISHING_RUN_USER_IDS` in
# `pipelex.system.telemetry.telemetry_identity`.
LOCAL_USER_ID = "local"
LOCAL_STORAGE_SCOPE = "local"

# The caller of every run on a server that has declared it has no users.
#
# pipelex-api attributes a request to this when its own configuration says there
# is no user model — no authentication, or one shared static key — so there is
# exactly one tenant and it has nobody to name. Like `LOCAL_USER_ID` it is a true
# statement rather than an unknown caller, and it is carried and stored as-is;
# like `LOCAL_USER_ID` it is also the same string on every such deployment, so
# telemetry declines it as a person. It is defined here so a host imports the
# one string the runtime recognises instead of spelling its own.
SINGLE_TENANT_USER_ID = "single-tenant"

# The leaf generated bytes land under, composed onto the scope by
# `GeneratedContentFactory`. It is a constant and not a config value on purpose:
# an operator who can omit the leaf can put generated content back at the root
# of the scope, and an invariant a config may switch off is not one.
#
# It is its own leaf rather than sharing `assets/` because the two differ in
# PROVENANCE — `assets/` is what the caller supplied, this is what the run
# produced — and that distinction is the one an operator needs to act on
# ("drop what we generated, keep what the user gave us"). It is not `results/`:
# that leaf is the delivery envelope, written once at the end under fixed names
# and only when storage delivery is configured, whereas this is written during
# the run, content-addressed, and mostly intermediate — a generated image is
# usually an input to a later step rather than an output of the pipeline.
GENERATED_CONTENT_LEAF = "generated"


def validate_storage_scope(*, value: str) -> str:
    """Return `value` if it is a usable storage scope, else raise `ValueError`.

    Raises:
        ValueError: the scope is empty, has more than three segments, or
            contains a segment that is not `[A-Za-z0-9_-]+` — which covers
            traversal (`..`), absolute paths, and empty segments.
    """
    # `fullmatch`, NOT `match`. A trailing `$` in a `match` still admits one
    # final newline, so `"org/mt/run\n"` passed this guard and the newline then
    # travelled into every storage key and log line built from the scope — a log
    # forging primitive, and a key nobody can address. `fullmatch` has no such
    # concession, which is why the anchors below are redundant but kept: the
    # pattern is also read on its own by the wire-level validators.
    if not STORAGE_SCOPE_PATTERN.fullmatch(value):
        msg = (
            f"Invalid storage_scope {value!r}: expected one to three path-safe segments "
            "separated by single slashes (e.g. 'tenant/run' or 'tenant/method/run'). "
            "Empty segments, '.', '..' and leading or trailing slashes are refused — "
            "the value becomes a storage key prefix, so a traversal in it escapes the tenant."
        )
        raise ValueError(msg)
    return value


def validate_read_scope(*, value: str) -> str:
    """Return `value` if it is a usable read scope, else raise `ValueError`.

    The same segment rule as the storage scope, which it must contain: one to
    three `[A-Za-z0-9_-]+` segments joined by single slashes, applied with
    `fullmatch` for the reason `validate_storage_scope` gives.

    Raises:
        ValueError: the scope is empty, has more than three segments, or
            contains a segment that is not `[A-Za-z0-9_-]+`.
    """
    if not STORAGE_SCOPE_PATTERN.fullmatch(value):
        msg = (
            f"Invalid read_scope {value!r}: expected one to three path-safe segments "
            "separated by single slashes (e.g. 'tenant'). Empty segments, '.', '..' and "
            "leading or trailing slashes are refused — the value bounds every storage key the run may read."
        )
        raise ValueError(msg)
    return value


def is_key_within_read_scope(*, key: str, read_scope: str) -> bool:
    """Whether the storage `key` lies under `read_scope`, compared segment by segment.

    By segment and never by string prefix, because `org_abc` is a string prefix
    of `org_abcdef`. The key's own segments are checked too: an empty, `.` or
    `..` segment, or a backslash, is refused wherever it sits, because the local
    storage provider resolves a key against a directory, where
    `org_a/../org_b/x.png` passes a lexical prefix test and reads from `org_b`,
    and a backslash is a separator on Windows.
    """
    if "\\" in key:
        return False
    key_segments = key.split("/")
    if any(segment in {"", ".", ".."} for segment in key_segments):
        return False
    scope_segments = read_scope.split("/")
    # Strictly longer than the scope: the scope names a namespace, and a key equal
    # to it names no object inside that namespace.
    return len(key_segments) > len(scope_segments) and key_segments[: len(scope_segments)] == scope_segments


def validate_storage_scope_within_read_scope(*, storage_scope: str, read_scope: str | None) -> None:
    """Raise `ValueError` if a run could not read what it writes.

    A run reads its own outputs back — a generated image shown to the next
    model, a page view of its own extraction — so a storage scope outside the
    read scope would make every such read a refusal. A host that passes the two
    mismatched fails here, at construction, rather than at the first read. An
    unscoped run (`read_scope` is `None`) reads everything and needs no check.

    Raises:
        ValueError: the storage scope does not lie under the read scope.
    """
    if read_scope is None:
        return
    storage_segments = storage_scope.split("/")
    scope_segments = read_scope.split("/")
    if storage_segments[: len(scope_segments)] != scope_segments:
        msg = (
            "The run's storage_scope does not lie under its read_scope: a run must be able to read "
            "what it writes. Pass a read_scope that is the storage_scope or one of its leading segments."
        )
        raise ValueError(msg)
