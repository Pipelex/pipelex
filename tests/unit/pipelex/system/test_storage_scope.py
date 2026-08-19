"""`storage_scope` — the construction-time guard on where a run's bytes go.

These are the tests that matter most in the storage change. The scope is pasted
straight into a storage key prefix, so a `..` or a leading slash in it is a path
traversal out of the tenant's namespace. Before this field existed, the Temporal
payload codec sanitized `user_id` and `pipeline_run_id` per-segment; collapsing
them into one slash-bearing string made that sanitizer unusable, so without
these checks the change would have silently deleted a traversal control.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from pydantic import ValidationError

from pipelex.system.job_metadata import JobMetadata
from pipelex.system.storage_scope import (
    DRY_RUN_STORAGE_SCOPE,
    DRY_RUN_USER_ID,
    LOCAL_STORAGE_SCOPE,
    LOCAL_USER_ID,
    validate_storage_scope,
)
from pipelex.system.telemetry.otel_constants import OTelConstants


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
        "scope",
        [
            pytest.param("", id="empty"),
            pytest.param("/tenant/run", id="leading-slash-absolute-key"),
            pytest.param("tenant/run/", id="trailing-slash-empty-final-segment"),
            pytest.param("tenant//run", id="empty-interior-segment"),
            pytest.param("..", id="traversal-alone"),
            pytest.param("tenant/../other", id="traversal-interior"),
            pytest.param("../other/run", id="traversal-leading"),
            pytest.param(".", id="current-dir-segment"),
            pytest.param("tenant/./run", id="current-dir-interior"),
            pytest.param("a/b/c/d", id="four-segments-would-swallow-the-leaf"),
            pytest.param("tenant run", id="space"),
            pytest.param("tenant?x=1", id="query-string"),
            pytest.param("tenant#frag", id="fragment"),
            pytest.param("tenant\\run", id="backslash"),
            pytest.param("tenant%2f..%2f", id="percent-encoded-traversal"),
            # A `$`-anchored `re.match` admits ONE trailing newline, so these
            # passed the guard and the newline travelled into every storage key
            # and log line built from the scope — an unaddressable key and a log
            # forging primitive. `fullmatch` is what closes it; these pin it shut.
            pytest.param("tenant/run\n", id="trailing-newline"),
            pytest.param("tenant\n", id="single-segment-trailing-newline"),
            pytest.param("tenant\nrun", id="interior-newline"),
            pytest.param("tenant/run\r", id="trailing-carriage-return"),
            pytest.param("tenant/run\r\n", id="trailing-crlf"),
            pytest.param("\n", id="newline-alone"),
        ],
    )
    def test_unsafe_scopes_raise_at_construction(self, scope: str) -> None:
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
            # Both type checkers reject this call, which is the point being
            # tested: the omission is caught statically AND at runtime. The
            # ignores are what let the runtime half be asserted at all.
            JobMetadata(user_id="u1", pipeline_run_id="run_1")  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]


class TestTheTelemetryPlaceholderStaysOutOfIdentity:
    """`OTelConstants.DEFAULT_USER_ID` is `"anonymous"`, and it is TELEMETRY.

    It means "a span with no known caller". It leaked into the identity path,
    became the first segment of every storage key a run without an authenticated
    caller wrote, and put every such tenant into one namespace where each could
    read the others' outputs. The failure was silent by construction: a missing
    identity looked exactly like a present one.

    The constant survives because tracing genuinely has that concept. These tests
    are what keep it there — a future `user_id or DEFAULT_USER_ID` is the exact
    regression they exist to catch, and it would otherwise be invisible until
    someone read an S3 bucket listing.
    """

    def test_no_module_uses_it_as_an_identity_or_a_scope(self) -> None:
        source_root = Path(__file__).resolve().parents[4] / "pipelex"
        assert source_root.is_dir(), source_root

        offenders: list[str] = []
        for path in source_root.rglob("*.py"):
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if line.lstrip().startswith("#"):
                    continue
                # The optional `: <annotation>` matters: a parameter default is written
                # `user_id: str = OTelConstants.DEFAULT_USER_ID`, and a pattern
                # without it passes a real regression while looking like a guard.
                if re.search(r"\b(user_id|storage_scope)\b\s*(?::[^=]+)?=\s*[\w.]*DEFAULT_USER_ID", line):
                    offenders.append(f"{path.relative_to(source_root)}:{line_number}")

        assert not offenders, (
            "The telemetry placeholder is being bound as an identity or a storage scope at "
            f"{offenders}. It is the string 'anonymous'; using it here is how every "
            "unauthenticated run ended up sharing one storage namespace. Use DRY_RUN_USER_ID "
            "or LOCAL_USER_ID, or require the caller to supply one."
        )

    def test_the_dry_run_identity_is_not_the_telemetry_placeholder(self) -> None:
        """They mean different things and must not converge back onto one string."""
        assert DRY_RUN_USER_ID != OTelConstants.DEFAULT_USER_ID
        assert LOCAL_USER_ID != OTelConstants.DEFAULT_USER_ID
