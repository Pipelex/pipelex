"""`storage_scope` — the construction-time guard on where a run's bytes go.

These are the tests that matter most in the storage change. The scope is pasted
straight into a storage key prefix, so a `..` or a leading slash in it is a path
traversal out of the tenant's namespace. Before this field existed, the Temporal
payload codec sanitized `user_id` and `pipeline_run_id` per-segment; collapsing
them into one slash-bearing string made that sanitizer unusable, so without
these checks the change would have silently deleted a traversal control.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.system.job_metadata import JobMetadata
from pipelex.system.storage_scope import (
    DRY_RUN_STORAGE_SCOPE,
    LOCAL_STORAGE_SCOPE,
    validate_storage_scope,
)


def _metadata(storage_scope: str) -> JobMetadata:
    return JobMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope=storage_scope)


class TestAcceptedScopes:
    @pytest.mark.parametrize(
        "scope",
        [
            "tenant",
            "tenant/run_1",
            "org_acme/mt_x/run_1",
            "A-Z_az-09",
            DRY_RUN_STORAGE_SCOPE,
            LOCAL_STORAGE_SCOPE,
        ],
    )
    def test_one_to_three_path_safe_segments_are_accepted(self, scope: str) -> None:
        assert _metadata(scope).storage_scope == scope

    def test_the_two_named_constants_are_valid_scopes(self) -> None:
        """They are used as real field values, so they must satisfy the field.

        A constant that the validator rejects would turn every dry run into a
        `ValidationError` — and dry runs are the validation path, so the failure
        would surface as "your bundle is invalid".
        """
        assert validate_storage_scope(value=DRY_RUN_STORAGE_SCOPE)
        assert validate_storage_scope(value=LOCAL_STORAGE_SCOPE)


class TestRefusedScopes:
    @pytest.mark.parametrize(
        ("scope", "why"),
        [
            ("", "empty"),
            ("/tenant/run", "leading slash — an absolute key"),
            ("tenant/run/", "trailing slash — an empty final segment"),
            ("tenant//run", "empty interior segment"),
            ("..", "traversal, alone"),
            ("tenant/../other", "traversal, interior"),
            ("../other/run", "traversal, leading"),
            (".", "current-dir segment"),
            ("tenant/./run", "current-dir segment, interior"),
            ("a/b/c/d", "four segments would swallow the leaf the runtime appends"),
            ("tenant run", "space"),
            ("tenant?x=1", "query string"),
            ("tenant#frag", "fragment"),
            ("tenant\\run", "backslash"),
            ("tenant%2f..%2f", "percent-encoded traversal"),
        ],
    )
    def test_unsafe_scopes_raise_at_construction(self, scope: str, why: str) -> None:
        """Refused when the object is BUILT, not when the key is written.

        The distinction is the whole design: a `JobMetadata` that exists is a
        `JobMetadata` whose scope is safe, so every key derived downstream is
        safe by construction rather than by each call site remembering.
        """
        with pytest.raises(ValidationError):
            _metadata(scope)

    def test_a_prefix_of_another_tenant_is_still_its_own_scope(self) -> None:
        """The validator checks SHAPE, never ownership — that is the host's job.

        Recorded so nobody mistakes this for the tenant boundary. `tenant2` is a
        perfectly valid scope even when the caller is `tenant`; refusing it
        requires knowing who is calling, which this layer deliberately does not.
        """
        assert _metadata("tenant2/run_1").storage_scope == "tenant2/run_1"


class TestScopeIsRequired:
    def test_omitting_it_is_an_error_rather_than_a_default(self) -> None:
        """No default, deliberately.

        A default here is how the shared `anonymous/` namespace grew the first
        time: a placeholder that was never meant to reach storage became the key
        prefix for every run without an authenticated caller, and each tenant
        could read the others' outputs. A missing scope must be a loud failure
        at the call site, not a quiet shared prefix in production.
        """
        with pytest.raises(ValidationError):
            JobMetadata(user_id="u1", pipeline_run_id="run_1")  # pyright: ignore[reportCallIssue]
