"""`storage_scope` — the one opaque string that decides where a run's bytes go.

**The runtime does not know what an organization or a method is, and must not
learn.** A host that runs Pipelex for many tenants needs every object a run
writes to land inside that tenant's namespace; Pipelex needs to compose leaves
(`assets/`, `results/`, `payloads/`) onto *something*. `storage_scope` is that
something: an opaque, host-supplied prefix that the runtime treats as a unit.

The hosted Pipelex platform fills it with `<org_id>/<method_id>/<run_id>`, but
nothing here knows or checks that — a single-user deployment can pass
`<user_id>/<run_id>` and a local one can pass `local/<run_id>`. Threading the
host's own concepts through the transport instead was considered and rejected:
`method_id` is a hosted catalog concept with no meaning in an MIT-licensed
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
"""

from __future__ import annotations

import re

# One to three `[A-Za-z0-9_-]` segments joined by single slashes.
#
# Rejects, in one rule: the empty string, a leading or trailing slash, an empty
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
LOCAL_USER_ID = "local"
LOCAL_STORAGE_SCOPE = "local"


def validate_storage_scope(*, value: str) -> str:
    """Return `value` if it is a usable storage scope, else raise `ValueError`.

    Raises:
        ValueError: the scope is empty, has more than three segments, or
            contains a segment that is not `[A-Za-z0-9_-]+` — which covers
            traversal (`..`), absolute paths, and empty segments.
    """
    if not STORAGE_SCOPE_PATTERN.match(value):
        msg = (
            f"Invalid storage_scope {value!r}: expected one to three path-safe segments "
            "separated by single slashes (e.g. 'tenant/run' or 'tenant/method/run'). "
            "Empty segments, '.', '..' and leading or trailing slashes are refused — "
            "the value becomes a storage key prefix, so a traversal in it escapes the tenant."
        )
        raise ValueError(msg)
    return value
