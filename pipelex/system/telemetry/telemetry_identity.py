"""`TelemetryIdentity` — who a span or an event is attributed to, on one stream.

**Identity is a fact of the run, not of the process.** A `TelemetryManager` binds
one `distinct_id` when it is built — the operator's configured `user_id` — and
before this module every span and every event carried that one id. On a host that serves many callers from one
process that is exactly wrong: every tenant's generations land under one identity
per deployment. The runtime already knows who each run belongs to, on
`RunMetadata.user_id`, and what it belongs to, on `RunMetadata.analytics_groups`;
this module is the single place that turns those two facts into what a capture
needs.

**One resolution, applied everywhere.** The exporter resolves per span, the
tracker per event, and both go through `TelemetryIdentity` so they cannot drift.
What the stream may do with a run's identity is its `RunIdentityPolicy`, and
there are two, read from the operator's PostHog mode:

1. `NONE` — the capture is anonymous whatever the run says, and the caller marks
   it so. No user, no fallback, no groups.
2. `DIRECT` — the run's own `user_id` is the `distinct_id`, spelled as the
   operator's own backend already knows it, and the run's groups ride the
   capture.

**A run that names nobody** reports under the stream's configured fallback, and
so does an event that belongs to no run at all — a CLI command, a dry-run sweep.
`RunMetadata.user_id` is required, but some of its values name a caller without
distinguishing one; see `_NON_DISTINGUISHING_RUN_USER_IDS` below. This is why a
local run keeps reporting exactly as it did before per-run attribution existed.
Under `DIRECT` the run's groups still ride such a capture: a host may know which
entities a run belongs to without naming its caller, and the two facts are
independent.

**Where the identity is NOT.** The user id goes on the capture as `distinct_id`
and the groups go through the capture's `groups` argument. Neither is ever copied
into an event property or a span name: one field, one meaning, and a second copy
is a second thing to keep in step.
"""

import json
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from pipelex.system.storage_scope import DRY_RUN_USER_ID, LOCAL_USER_ID, SINGLE_TENANT_USER_ID
from pipelex.system.telemetry.otel_constants import LangfuseSpanAttr, PipelexSpanAttr
from pipelex.system.telemetry.telemetry_config import PostHogMode
from pipelex.tools.log.log import log
from pipelex.tools.misc.json_utils import pure_json_str

if TYPE_CHECKING:
    from pipelex.system.job_metadata import RunMetadata


# The `user_id` values that name a caller without distinguishing one, and must
# therefore never become a `distinct_id`.
#
# `RunMetadata.user_id` is required precisely so that a host must state who is
# running — but the two constructor defaults in
# :mod:`pipelex.system.storage_scope`, and the single-tenant id a host without a
# user model states, are true statements rather than identities a backend can
# tell apart. `LOCAL_USER_ID` is the literal "local", the same
# string on every machine on earth: honoured as a `distinct_id` it would collapse
# every Pipelex user's local runs onto one person. `DRY_RUN_USER_ID`
# says outright that there is no caller. `SINGLE_TENANT_USER_ID` is what
# pipelex-api states for every run on a deployment configured with no users, and
# is as global as `"local"`.
#
# So for telemetry these mean "this run names nobody", and the stream's own
# fallback answers instead: the operator's configured `user_id` — which is exactly
# what a CLI run reported under before per-run attribution existed, and still does.
_NON_DISTINGUISHING_RUN_USER_IDS = frozenset({LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID})


class RunIdentityPolicy(StrEnum):
    """What the operator's stream may do with a run's identity.

    The stream reports into the operator's own PostHog project. A caller's
    `user_id` there is a value they already hold and a group key is their own
    vocabulary, so `DIRECT` sends both as they are — and `anonymous` mode turns
    the whole thing off with `NONE`, because an operator who chose to identify
    nobody chose it for their users too.
    """

    NONE = "none"
    DIRECT = "direct"

    @classmethod
    def make_for_operator_stream(cls, *, posthog_mode: PostHogMode) -> "RunIdentityPolicy":
        """The policy an operator's own stream carries, read from the mode they set.

        Stated once, because the operator's stream resolves an identity from
        three places — the event tracker, the trace-start capture and the span
        exporter — and a mode that meant one thing in one of them and something
        else in another is exactly the drift this module exists to prevent.
        """
        return cls.DIRECT if posthog_mode.is_identified else cls.NONE


def make_run_identity_span_attributes(*, run_metadata: "RunMetadata", is_langfuse_enabled: bool) -> dict[str, str]:
    """Build the span attributes that carry a run's identity to every exporter.

    Called at each span site from the `JobMetadata` already in hand, so the
    identity travels on the span object through the batch processor: no exporter
    has to correlate a span back to a run through shared state, and every
    exporter sees the same fact. PostHog is the one that reads the groups as
    group identity; Langfuse gets the user id in the field it reserves for it,
    which it has defined and never received until now.

    Args:
        run_metadata: The run half of the job metadata the span site holds.
        is_langfuse_enabled: Whether the Langfuse exporter is configured, which
            is the only reason to spend an attribute on Langfuse's spelling of
            the same value.

    Returns:
        The attributes to merge into the span's attribute dict. The groups entry
        is absent — not empty — when the run carries no groups. `pipelex.run.user_id`
        is written as the run states it, placeholders included: a span attribute
        records what the run IS, and whether that value may be attributed to a
        person is a separate decision, taken once in `_resolve` below. Langfuse's
        own field is the opposite case — it IS that decision, with no `_resolve`
        behind it to take it later — so a placeholder is withheld from it rather
        than becoming a person named `local` in the operator's project.
    """
    attributes: dict[str, str] = {PipelexSpanAttr.RUN_USER_ID: run_metadata.user_id}
    if run_metadata.analytics_groups:
        attributes[PipelexSpanAttr.RUN_ANALYTICS_GROUPS] = pure_json_str(data=run_metadata.analytics_groups)
    if is_langfuse_enabled and run_metadata.user_id not in _NON_DISTINGUISHING_RUN_USER_IDS:
        attributes[LangfuseSpanAttr.USER_ID] = run_metadata.user_id
    return attributes


class TelemetryIdentity(BaseModel):
    """The resolved attribution of one capture on one stream.

    Frozen, because it is a decision already taken: a capture path reads it, it
    never edits it.
    """

    model_config = ConfigDict(frozen=True)

    # The identity the capture is sent under, or None for an anonymous capture.
    distinct_id: str | None = None

    # The entities the capture belongs to, forwarded through the backend's own
    # groups facet. Empty on an anonymous capture, which has no person for a
    # group to qualify.
    groups: dict[str, str] = Field(default_factory=dict)

    @property
    def is_anonymous(self) -> bool:
        """Whether this capture has no person to attribute itself to."""
        return not self.distinct_id

    @classmethod
    def make_anonymous(cls) -> "TelemetryIdentity":
        """The identity of a stream that identifies nobody, whatever the run says."""
        return cls(distinct_id=None, groups={})

    @classmethod
    def _resolve(
        cls,
        *,
        run_user_id: str | None,
        run_groups: dict[str, str] | None,
        fallback_distinct_id: str | None,
        run_identity_policy: RunIdentityPolicy,
    ) -> "TelemetryIdentity":
        """The one resolution, stated once — see this module's docstring for the two cases."""
        if run_identity_policy is RunIdentityPolicy.NONE:
            return cls.make_anonymous()

        distinguishing_user_id = run_user_id if run_user_id and run_user_id not in _NON_DISTINGUISHING_RUN_USER_IDS else None

        resolved_distinct_id = distinguishing_user_id or fallback_distinct_id
        if not resolved_distinct_id:
            return cls.make_anonymous()
        return cls(distinct_id=resolved_distinct_id, groups=dict(run_groups or {}))

    @classmethod
    def make_from_run_metadata(
        cls,
        *,
        run_metadata: "RunMetadata | None",
        fallback_distinct_id: str | None,
        run_identity_policy: RunIdentityPolicy,
    ) -> "TelemetryIdentity":
        """Resolve the attribution of an event, from the run that produced it.

        Args:
            run_metadata: The run half of the metadata the emitter holds, or None
                for an event that belongs to no run — a CLI command, a dry-run
                sweep, the "telemetry just enabled" notice.
            fallback_distinct_id: The identity this stream falls back to.
            run_identity_policy: What this stream may do with the run's identity.
        """
        return cls._resolve(
            run_user_id=run_metadata.user_id if run_metadata is not None else None,
            run_groups=run_metadata.analytics_groups if run_metadata is not None else None,
            fallback_distinct_id=fallback_distinct_id,
            run_identity_policy=run_identity_policy,
        )

    @classmethod
    def make_from_span_attributes(
        cls,
        *,
        attributes: Mapping[str, Any],
        fallback_distinct_id: str | None,
        run_identity_policy: RunIdentityPolicy,
    ) -> "TelemetryIdentity":
        """Resolve the attribution of a span, from the attributes it carries.

        The counterpart of `make_run_identity_span_attributes`: a span produced
        before this release, or by a code path that sets no identity, simply
        carries neither attribute and resolves to the stream's fallback.
        """
        run_user_id = attributes.get(PipelexSpanAttr.RUN_USER_ID)
        return cls._resolve(
            run_user_id=run_user_id if isinstance(run_user_id, str) else None,
            run_groups=cls._read_groups_attribute(attributes=attributes),
            fallback_distinct_id=fallback_distinct_id,
            run_identity_policy=run_identity_policy,
        )

    @classmethod
    def _read_groups_attribute(cls, *, attributes: Mapping[str, Any]) -> dict[str, str]:
        """Read back the groups a span site serialized, refusing anything else.

        The value was written by `make_run_identity_span_attributes` from an
        already-validated mapping, so a shape other than a JSON object of strings
        means the span was built by something else. Telemetry never breaks the
        app, so that is a debug line and an empty mapping — the span still
        exports, attributed to the run's user without its groups.
        """
        raw = attributes.get(PipelexSpanAttr.RUN_ANALYTICS_GROUPS)
        if raw is None:
            return {}
        if not isinstance(raw, str):
            log.debug(f"Ignoring span attribute '{PipelexSpanAttr.RUN_ANALYTICS_GROUPS}': expected a JSON string, got {type(raw).__name__}")
            return {}
        try:
            decoded = json.loads(raw)
        except ValueError as exc:
            log.debug(f"Ignoring span attribute '{PipelexSpanAttr.RUN_ANALYTICS_GROUPS}': not decodable JSON ({exc})")
            return {}
        if not isinstance(decoded, dict):
            log.debug(f"Ignoring span attribute '{PipelexSpanAttr.RUN_ANALYTICS_GROUPS}': expected a JSON object, got {type(decoded).__name__}")
            return {}
        groups: dict[str, str] = {}
        for group_type, group_key in decoded.items():  # type: ignore[union-attr]
            if isinstance(group_type, str) and isinstance(group_key, str):
                groups[group_type] = group_key
            else:
                log.debug(f"Ignoring a non-string entry in span attribute '{PipelexSpanAttr.RUN_ANALYTICS_GROUPS}'")
        return groups
