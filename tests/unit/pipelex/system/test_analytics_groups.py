"""`analytics_groups` — the construction-time guard on the host's opaque group labels.

The mapping is host-supplied and arrives over a wire, so it is exactly the kind
of value that must be refused at the type rather than three frames into a run.
It is also *never read by name* here: the runtime forwards it to whichever
telemetry consumer understands groups and learns nothing about what an
`organization` is. That makes the charset and the size bound the only thing
standing between a caller's mistake and a telemetry backend, which is what these
tests pin.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.system.analytics_groups import (
    ANALYTICS_GROUP_KEY_PATTERN,
    ANALYTICS_GROUP_TYPE_PATTERN,
    ANALYTICS_GROUPS_MAX_ENTRIES,
    validate_analytics_groups,
)
from pipelex.system.job_metadata import JobMetadata, RunMetadata


def _metadata(analytics_groups: dict[str, str]) -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(
            user_id="u1",
            pipeline_run_id="run_1",
            storage_scope="tenant/run_1",
            analytics_groups=analytics_groups,
        )
    )


class TestAnalyticsGroups:
    @pytest.mark.parametrize(
        "groups",
        [
            pytest.param({}, id="empty-mapping"),
            pytest.param({"organization": "org_acme"}, id="the-hosted-plane-shape"),
            pytest.param({"organization": "org_acme", "workspace": "ws-1"}, id="two-group-types"),
            pytest.param({"a": "x"}, id="shortest-key-and-value"),
            pytest.param({"a_b_c9": "A-Z_az-09"}, id="full-charset"),
            pytest.param({"a" * 32: "v" * 128}, id="longest-key-and-value"),
            pytest.param({f"g{index}": "v" for index in range(ANALYTICS_GROUPS_MAX_ENTRIES)}, id="at-the-entry-cap"),
        ],
    )
    def test_well_formed_groups_are_accepted(self, groups: dict[str, str]) -> None:
        assert _metadata(groups).run_metadata.analytics_groups == groups

    def test_an_empty_mapping_is_the_default(self) -> None:
        """Unlike `user_id` and `storage_scope`, this field defaults.

        An absent group creates no shared namespace and misattributes nothing —
        it only leaves the group facet empty. The doctrine that made the other
        two required is about IDENTITY, and identity is still non-defaulting.
        """
        run_metadata = RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope="tenant/run_1")
        assert run_metadata.analytics_groups == {}

    def test_two_run_metadatas_do_not_share_one_default_mapping(self) -> None:
        """A mutable default shared between instances would let one run's groups leak into another."""
        first = RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope="tenant/run_1")
        second = RunMetadata(user_id="u2", pipeline_run_id="run_2", storage_scope="tenant/run_2")
        first.analytics_groups["organization"] = "org_acme"
        assert second.analytics_groups == {}

    @pytest.mark.parametrize(
        "groups",
        [
            pytest.param({"Organization": "org_acme"}, id="uppercase-key"),
            pytest.param({"9org": "org_acme"}, id="key-starting-with-a-digit"),
            pytest.param({"_org": "org_acme"}, id="key-starting-with-an-underscore"),
            pytest.param({"": "org_acme"}, id="empty-key"),
            pytest.param({"org-id": "org_acme"}, id="hyphen-in-key"),
            pytest.param({"org id": "org_acme"}, id="space-in-key"),
            pytest.param({"org.id": "org_acme"}, id="dot-in-key"),
            pytest.param({"a" * 33: "org_acme"}, id="key-one-over-the-length-cap"),
            pytest.param({"organization": ""}, id="empty-value"),
            pytest.param({"organization": "org acme"}, id="space-in-value"),
            pytest.param({"organization": "org/acme"}, id="slash-in-value"),
            pytest.param({"organization": "org.acme"}, id="dot-in-value"),
            # A `$`-anchored `re.match` admits one trailing newline, which is a log
            # forging primitive once the value is quoted into a log line. The
            # validator uses `fullmatch`; these pin it shut, as they do for
            # `storage_scope`.
            pytest.param({"organization": "org_acme\n"}, id="trailing-newline-in-value"),
            pytest.param({"organization": "org\nacme"}, id="interior-newline-in-value"),
            pytest.param({"organization": "org_acme\r"}, id="trailing-carriage-return-in-value"),
            pytest.param({"organization\n": "org_acme"}, id="trailing-newline-in-key"),
            pytest.param({"organization": "v" * 129}, id="value-one-over-the-length-cap"),
            pytest.param({f"g{index}": "v" for index in range(ANALYTICS_GROUPS_MAX_ENTRIES + 1)}, id="one-over-the-entry-cap"),
        ],
    )
    def test_malformed_groups_raise_at_construction(self, groups: dict[str, str]) -> None:
        """Refused when the object is BUILT, not when a telemetry consumer chokes on it.

        Same reasoning as `storage_scope`: a `RunMetadata` that exists is one
        whose groups are safe to forward, so no downstream exporter has to
        re-check them.
        """
        with pytest.raises(ValidationError):
            _metadata(groups)

    def test_the_error_names_the_offending_entry(self) -> None:
        """The caller supplied the mapping, so the message must say which entry it got wrong."""
        with pytest.raises(ValidationError, match="Organization"):
            _metadata({"Organization": "org_acme"})

    def test_an_unknown_group_type_is_carried_through(self) -> None:
        """No key is privileged: `organization` is the hosted plane's word, not the runtime's.

        The runtime is forbidden to learn what an organization is — the same rule
        that keeps `storage_scope` opaque — so a group type it has never heard of
        must travel exactly as well as the one the platform happens to send.
        """
        groups = {"tenant": "t-1", "plan_tier": "enterprise"}
        assert _metadata(groups).run_metadata.analytics_groups == groups

    def test_copy_with_update_carries_the_groups_through(self) -> None:
        """`copy_with_update` replaces the per-job half and carries the run half intact.

        A nested pipe's span is part of the same run, so it must attribute to the
        same groups. Losing them here would leave the group facet empty for every
        span but the outermost one.
        """
        parent = _metadata({"organization": "org_acme"})
        child = parent.copy_with_update(otel_context=None, pipe_code="nested_pipe")
        assert child.run_metadata.analytics_groups == {"organization": "org_acme"}
        assert child.pipe_code == "nested_pipe"

    def test_the_copy_does_not_alias_the_parents_mapping(self) -> None:
        """`copy_with_update` deep-copies, so a child mutating its groups cannot reach the parent."""
        parent = _metadata({"organization": "org_acme"})
        child = parent.copy_with_update(otel_context=None)
        child.run_metadata.analytics_groups["organization"] = "org_other"
        assert parent.run_metadata.analytics_groups == {"organization": "org_acme"}

    def test_the_helper_returns_the_mapping_it_was_given(self) -> None:
        groups = {"organization": "org_acme"}
        assert validate_analytics_groups(value=groups) == groups

    def test_the_helper_raises_value_error_rather_than_a_pydantic_error(self) -> None:
        """It is shared by the field validator and the wire payload, so it speaks stdlib."""
        with pytest.raises(ValueError, match="analytics_groups"):
            validate_analytics_groups(value={"Organization": "org_acme"})

    def test_the_patterns_are_anchored_by_fullmatch_not_by_the_dollar_sign(self) -> None:
        """`re.match` with a trailing `$` accepts one final newline; `fullmatch` does not."""
        assert ANALYTICS_GROUP_TYPE_PATTERN.match("organization\n") is not None
        assert ANALYTICS_GROUP_TYPE_PATTERN.fullmatch("organization\n") is None
        assert ANALYTICS_GROUP_KEY_PATTERN.match("org_acme\n") is not None
        assert ANALYTICS_GROUP_KEY_PATTERN.fullmatch("org_acme\n") is None
