"""`read_scope` on `RunMetadata` — the host-supplied prefix bounding what a run may read.

The check itself is `pipelex.tools.uri.uri_read_scope`; these tests pin the value's own guards: it is
required, it is a path-safe prefix, and the run's storage scope lies under it, since a run reads its
own outputs back.
"""

import pytest
from pydantic import ValidationError

from pipelex.system.job_metadata import RunMetadata


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
