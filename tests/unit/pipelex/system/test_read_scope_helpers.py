"""The storage-scope module's read-scope helpers: validation, containment, and the segment-wise key check."""

import pytest

from pipelex.system.storage_scope import is_key_within_read_scope, validate_read_scope, validate_storage_scope_within_read_scope


class TestReadScopeHelpers:
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
