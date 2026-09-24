"""Unit tests for the one resolution every capture path shares.

`TelemetryIdentity` is where "who is this capture for" is decided, for both
PostHog streams and for events as well as spans. The matrix below is the whole
contract, and it is a matrix of `RunIdentityPolicy` against what the run names:

- `NONE` captures anonymously whatever the run says, which is what an operator
  asking to identify nobody asked for.
- `DIRECT` takes the run's own user, or the stream's fallback when the run names
  nobody, and carries the run's groups either way. Pipelex's own stream is
  always `DIRECT`.

The span-attribute half is the round trip: what a span site writes is what the
exporter reads back, and a span that carries nothing resolves to the fallback —
which is what every span produced before this release does.
"""

import pytest

from pipelex.system.caller_identity import CallerIdentity
from pipelex.system.job_metadata import RunMetadata
from pipelex.system.storage_scope import DRY_RUN_USER_ID, LOCAL_USER_ID, SINGLE_TENANT_USER_ID
from pipelex.system.telemetry.otel_constants import LangfuseSpanAttr, PipelexSpanAttr
from pipelex.system.telemetry.telemetry_config import PostHogMode
from pipelex.system.telemetry.telemetry_identity import (
    RunIdentityPolicy,
    StreamIdentityRule,
    TelemetryIdentity,
    make_run_identity_span_attributes,
)


def _run_metadata(*, user_id: str = "user-42", extras: dict[str, str] | None = None) -> RunMetadata:
    return RunMetadata(
        user_id=user_id,
        pipeline_run_id="run-1",
        storage_scope="tenant/run-1",
        extras=extras or {},
    )


class TestTelemetryIdentity:
    # ----------------------------------------------------------------- DIRECT

    def test_a_direct_stream_takes_the_runs_user_and_groups(self) -> None:
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "user-42"
        assert identity.groups == {"organization": "org_acme"}

    def test_an_event_with_no_run_falls_back_to_the_configured_id(self) -> None:
        """A CLI command or a dry-run sweep has no run — the configured id is what it reports under."""
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=None,
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "configured-id"
        assert identity.groups == {}
        assert identity.is_anonymous is False

    def test_no_run_and_no_fallback_is_anonymous(self) -> None:
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=None,
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id is None
        assert identity.groups == {}
        assert identity.is_anonymous is True

    def test_a_run_without_groups_is_identified_with_an_empty_facet(self) -> None:
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(),
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "user-42"
        assert identity.groups == {}

    def test_the_groups_are_copied_not_shared_with_the_run(self) -> None:
        """The identity is a decision already taken; editing it must not reach back into the run."""
        run_metadata = _run_metadata(extras={"organization": "org_acme"})
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=run_metadata,
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        identity.groups["tenant"] = "t-1"

        assert run_metadata.extras == {"organization": "org_acme"}

    # ------------------------------------------------------------------- NONE

    def test_a_none_stream_sends_no_identity_at_all_even_with_a_fallback_configured(self) -> None:
        """An operator who chose `anonymous` chose it for their users AND for themselves.

        The fallback is the configured `user_id`, which `anonymous` mode does not
        forbid — an operator may set one, switch modes, and leave it behind. If
        the fallback still reached the capture, a mode whose documented promise is
        that the runtime identifies nobody would create a person profile on every
        span and on the trace-start event.
        """
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.NONE,
        )

        assert identity.distinct_id is None
        assert identity.is_anonymous is True
        assert identity.groups == {}

    def test_a_none_stream_ignores_a_spans_identity_and_its_fallback(self) -> None:
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={
                PipelexSpanAttr.RUN_USER_ID: "user-42",
                PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme"}',
            },
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.NONE,
        )

        assert identity.is_anonymous is True
        assert identity.groups == {}

    def test_an_event_with_no_run_is_anonymous_on_a_none_stream(self) -> None:
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=None,
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.NONE,
        )

        assert identity.is_anonymous is True

    @pytest.mark.parametrize(
        ("posthog_mode", "expected_policy"),
        [
            (PostHogMode.IDENTIFIED, RunIdentityPolicy.DIRECT),
            (PostHogMode.ANONYMOUS, RunIdentityPolicy.NONE),
            (PostHogMode.OFF, RunIdentityPolicy.NONE),
        ],
    )
    def test_an_operator_stream_reads_its_policy_off_the_mode(self, posthog_mode: PostHogMode, expected_policy: RunIdentityPolicy) -> None:
        assert RunIdentityPolicy.make_for_operator_stream(posthog_mode=posthog_mode) is expected_policy

    # ------------------------------------------ user ids that distinguish nobody

    @pytest.mark.parametrize("placeholder", [LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID])
    def test_a_placeholder_user_id_falls_back_to_the_stream(self, placeholder: str) -> None:
        """`RunMetadata.user_id` is required, so a caller with no real identity says so with a constant.

        Both constants are the SAME STRING on every machine. Honouring `"local"`
        as a `distinct_id` would merge every Pipelex user's local runs into one
        person, and would silently replace an operator's configured id with a
        literal on theirs.
        """
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(user_id=placeholder),
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "configured-id"

    @pytest.mark.parametrize("placeholder", [LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID])
    def test_a_placeholder_user_id_keeps_the_runs_groups(self, placeholder: str) -> None:
        """A host may know which entities a run belongs to without naming its caller.

        The two facts are independent: groups carry no person identity, so tying
        them to the distinguishing-user test discarded them from every capture of
        a run that simply left `user_id` at its default — which is what
        `PipelexRunner(extras=...)` does by default.
        """
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(user_id=placeholder, extras={"organization": "org_acme"}),
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "configured-id"
        assert identity.groups == {"organization": "org_acme"}

    @pytest.mark.parametrize("placeholder", [LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID])
    def test_a_span_carrying_a_placeholder_falls_back_too(self, placeholder: str) -> None:
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={PipelexSpanAttr.RUN_USER_ID: placeholder},
            fallback_distinct_id="gateway-hash",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "gateway-hash"

    @pytest.mark.parametrize("placeholder", [LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID])
    def test_a_placeholder_with_no_fallback_is_anonymous_not_the_placeholder(self, placeholder: str) -> None:
        identity = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(user_id=placeholder),
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.is_anonymous is True

    # -------------------------------------------------------- span attributes

    def test_a_run_with_groups_writes_both_attributes(self) -> None:
        attributes = make_run_identity_span_attributes(
            run_metadata=_run_metadata(extras={"organization": "org_acme"}),
            is_langfuse_enabled=False,
        )

        assert attributes[PipelexSpanAttr.RUN_USER_ID] == "user-42"
        assert attributes[PipelexSpanAttr.RUN_EXTRAS] == '{"organization": "org_acme"}'
        assert LangfuseSpanAttr.USER_ID not in attributes

    def test_a_run_without_groups_omits_the_groups_attribute(self) -> None:
        """Absent, not `{}`: an empty attribute on every span of every run is noise."""
        attributes = make_run_identity_span_attributes(run_metadata=_run_metadata(), is_langfuse_enabled=False)

        assert attributes[PipelexSpanAttr.RUN_USER_ID] == "user-42"
        assert PipelexSpanAttr.RUN_EXTRAS not in attributes

    def test_langfuse_gets_the_user_id_in_the_field_it_reserves_for_it(self) -> None:
        attributes = make_run_identity_span_attributes(run_metadata=_run_metadata(), is_langfuse_enabled=True)

        assert attributes[LangfuseSpanAttr.USER_ID] == "user-42"

    @pytest.mark.parametrize("placeholder", [LOCAL_USER_ID, DRY_RUN_USER_ID, SINGLE_TENANT_USER_ID])
    def test_langfuse_is_never_handed_a_placeholder_as_a_person(self, placeholder: str) -> None:
        """`langfuse.user.id` IS the attribution decision, with no `_resolve` behind it to take it later.

        `pipelex.run.user_id` may carry a placeholder because something downstream
        still gets to decide what it means; Langfuse's field does not, so a
        placeholder there becomes a person literally named `local`.
        """
        attributes = make_run_identity_span_attributes(
            run_metadata=_run_metadata(user_id=placeholder),
            is_langfuse_enabled=True,
        )

        assert attributes[PipelexSpanAttr.RUN_USER_ID] == placeholder
        assert LangfuseSpanAttr.USER_ID not in attributes

    def test_what_a_span_site_writes_is_what_the_exporter_reads_back(self) -> None:
        run_metadata = _run_metadata(extras={"organization": "org_acme", "tenant": "t-1"})
        attributes = make_run_identity_span_attributes(run_metadata=run_metadata, is_langfuse_enabled=False)

        identity = TelemetryIdentity.make_from_span_attributes(
            attributes=attributes,
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "user-42"
        assert identity.groups == {"organization": "org_acme", "tenant": "t-1"}

    def test_a_span_carrying_no_identity_resolves_to_the_fallback(self) -> None:
        """Every span produced before this release, and every span from a site that sets nothing."""
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={PipelexSpanAttr.PIPE_CODE: "some_pipe"},
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "configured-id"
        assert identity.groups == {}

    def test_undecodable_groups_keep_the_user_and_drop_the_groups(self) -> None:
        """Telemetry never breaks the app: a malformed attribute costs the group facet, not the span."""
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={
                PipelexSpanAttr.RUN_USER_ID: "user-42",
                PipelexSpanAttr.RUN_EXTRAS: "not json at all",
            },
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "user-42"
        assert identity.groups == {}

    def test_a_json_value_that_is_not_an_object_drops_the_groups(self) -> None:
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={
                PipelexSpanAttr.RUN_USER_ID: "user-42",
                PipelexSpanAttr.RUN_EXTRAS: '["organization"]',
            },
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.groups == {}

    def test_non_string_entries_are_dropped_and_the_rest_kept(self) -> None:
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={
                PipelexSpanAttr.RUN_USER_ID: "user-42",
                PipelexSpanAttr.RUN_EXTRAS: '{"organization": "org_acme", "count": 3}',
            },
            fallback_distinct_id=None,
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.groups == {"organization": "org_acme"}

    def test_a_non_string_user_id_attribute_is_not_used_as_an_identity(self) -> None:
        identity = TelemetryIdentity.make_from_span_attributes(
            attributes={PipelexSpanAttr.RUN_USER_ID: 42},
            fallback_distinct_id="configured-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity.distinct_id == "configured-id"


class TestResolutionFromACaller:
    """A caller known without a run resolves exactly as a run naming the same caller would."""

    @pytest.mark.parametrize("policy", list(RunIdentityPolicy))
    @pytest.mark.parametrize("user_id", ["user-42", LOCAL_USER_ID, DRY_RUN_USER_ID])
    def test_a_caller_resolves_like_the_run_it_would_state(self, policy: RunIdentityPolicy, user_id: str) -> None:
        groups = {"organization": "org_acme"}

        from_caller = TelemetryIdentity.make_from_caller_identity(
            caller_identity=CallerIdentity(user_id=user_id, extras=groups),
            fallback_distinct_id="fallback-id",
            run_identity_policy=policy,
        )
        from_run = TelemetryIdentity.make_from_run_metadata(
            run_metadata=_run_metadata(user_id=user_id, extras=groups),
            fallback_distinct_id="fallback-id",
            run_identity_policy=policy,
        )

        assert from_caller == from_run

    def test_no_caller_resolves_to_the_fallback(self) -> None:
        identity = TelemetryIdentity.make_from_caller_identity(
            caller_identity=None,
            fallback_distinct_id="fallback-id",
            run_identity_policy=RunIdentityPolicy.DIRECT,
        )

        assert identity == TelemetryIdentity(distinct_id="fallback-id", groups={})

    def test_a_stream_rule_resolves_per_caller(self) -> None:
        rule = StreamIdentityRule(fallback_distinct_id="fallback-id", run_identity_policy=RunIdentityPolicy.DIRECT)

        assert rule.resolve(caller_identity=CallerIdentity(user_id="user-42")).distinct_id == "user-42"
        assert rule.resolve(caller_identity=None).distinct_id == "fallback-id"

    def test_an_anonymous_stream_rule_identifies_nobody(self) -> None:
        rule = StreamIdentityRule(fallback_distinct_id="fallback-id", run_identity_policy=RunIdentityPolicy.NONE)

        assert rule.resolve(caller_identity=CallerIdentity(user_id="user-42")).is_anonymous
