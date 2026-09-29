"""`read_scope` — the host-supplied prefix bounding what a run may read, checked where the run is built.

The check itself is `pipelex.tools.uri.uri_read_scope`; these tests pin the value's own guards: it is
required on every type that carries it, it is a path-safe prefix, and the run's storage scope lies
under it, since a run reads its own outputs back.
"""

import pytest
from pydantic import ValidationError

from pipelex.runtime_bridge.payloads import PipelexPipeRunInput
from pipelex.system.job_metadata import RunMetadata
from pipelex.system.storage_scope import is_key_within_read_scope, validate_read_scope, validate_storage_scope_within_read_scope


class TestRunMetadataReadScope:
    def test_omitting_it_is_an_error_rather_than_a_default(self) -> None:
        with pytest.raises(ValidationError, match="read_scope"):
            RunMetadata.model_validate({"user_id": "u1", "pipeline_run_id": "run_1", "storage_scope": "org_abc/mt_1/run_1"})

    def test_none_is_the_explicit_unscoped_statement(self) -> None:
        run_metadata = RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope="run_1", read_scope=None)
        assert run_metadata.read_scope is None

    @pytest.mark.parametrize(
        ("storage_scope", "read_scope"),
        [
            ("org_abc/mt_1/run_1", "org_abc"),
            ("org_abc/mt_1/run_1", "org_abc/mt_1"),
            ("org_abc/mt_1/run_1", "org_abc/mt_1/run_1"),
        ],
    )
    def test_a_storage_scope_under_the_read_scope_is_accepted(self, storage_scope: str, read_scope: str) -> None:
        run_metadata = RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope=storage_scope, read_scope=read_scope)
        assert run_metadata.read_scope == read_scope

    @pytest.mark.parametrize(
        ("storage_scope", "read_scope"),
        [
            ("org_other/mt_1/run_1", "org_abc"),
            # A string prefix is not a segment prefix.
            ("org_abcdef/mt_1/run_1", "org_abc"),
            # A read scope deeper than the storage scope cannot contain it.
            ("org_abc", "org_abc/mt_1"),
        ],
    )
    def test_a_storage_scope_outside_the_read_scope_is_refused_at_construction(self, storage_scope: str, read_scope: str) -> None:
        with pytest.raises(ValidationError, match="does not lie under its read_scope"):
            RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope=storage_scope, read_scope=read_scope)

    @pytest.mark.parametrize("read_scope", ["", "..", "org/../other", "/org", "org/", "a/b/c/d", "org\nabc"])
    def test_an_unsafe_read_scope_is_refused_at_construction(self, read_scope: str) -> None:
        with pytest.raises(ValidationError, match="Invalid read_scope"):
            RunMetadata(user_id="u1", pipeline_run_id="run_1", storage_scope="org/run_1", read_scope=read_scope)


class TestBridgePayloadReadScope:
    def test_omitting_it_is_an_error_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="read_scope"):
            PipelexPipeRunInput.model_validate({"pipe_code": "p", "user_id": "u1", "storage_scope": "org_abc/run_1"})

    def test_a_storage_scope_outside_the_read_scope_is_refused_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="does not lie under its read_scope"):
            PipelexPipeRunInput(pipe_code="p", user_id="u1", storage_scope="org_other/run_1", read_scope="org_abc")

    def test_an_unsafe_read_scope_is_refused_at_the_wire(self) -> None:
        with pytest.raises(ValidationError, match="Invalid read_scope"):
            PipelexPipeRunInput(pipe_code="p", user_id="u1", storage_scope="org_abc/run_1", read_scope="../org_abc")


class TestScopeHelpers:
    def test_validate_read_scope_returns_a_valid_value(self) -> None:
        assert validate_read_scope(value="org_abc") == "org_abc"

    def test_an_unscoped_run_needs_no_containment(self) -> None:
        validate_storage_scope_within_read_scope(storage_scope="anything/at/all", read_scope=None)

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            ("org_abc/assets/x.png", True),
            ("org_abc/x.png", True),
            ("org_abc", False),
            ("org_abcdef/x.png", False),
            ("org_abc/../org_other/x.png", False),
            ("org_abc/./x.png", False),
            ("org_abc//x.png", False),
            ("org_abc\\x.png", False),
        ],
    )
    def test_is_key_within_read_scope_compares_by_segment(self, key: str, expected: bool) -> None:
        assert is_key_within_read_scope(key=key, read_scope="org_abc") is expected
