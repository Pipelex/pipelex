"""Unit tests for `is_safe_user_id` — the single-segment, URI-safe id invariant.

`user_id` is the first path segment of every `pipelex-storage://<user_id>/...`
URI and S3 key. It must therefore be path-safe (no traversal) AND an
unambiguous single URI segment: a value carrying a URI gen-delim (`: / ? # [ ] @`)
parses differently under a raw split vs a standard URI parser, so the owner a
consumer resolves could disagree with the owner this server authorized.
"""

import pytest

from api.security import is_safe_user_id


class TestIsSafeUserId:
    @pytest.mark.parametrize(
        "user_id",
        [
            "11111111-1111-4111-8111-111111111111",  # bare uuid
            "user_11111111-1111-4111-8111-111111111111",  # prefixed scheme
            "user-123",
            "google.abc",  # dot is fine — not a URI delimiter, not a traversal segment
            "a" * 36,
        ],
    )
    def test_accepts_unambiguous_segments(self, user_id: str):
        assert is_safe_user_id(user_id) is True

    @pytest.mark.parametrize(
        "user_id",
        [
            "",  # empty
            ".",  # traversal
            "..",  # traversal
            "a/b",  # path separator
            "a\\b",  # backslash
            "with\x00null",  # C0 control
            "with\x7fdel",  # DEL
            # URI gen-delims — ambiguous when embedded in pipelex-storage://<id>/...
            "google#abc",  # fragment delimiter (urlparse owner -> "google")
            "user@example.com",  # userinfo delimiter (urlparse hostname -> "example.com")
            "a:99999",  # port delimiter
            "a?b",  # query delimiter
            "a[b]",  # IPv6-literal brackets
        ],
    )
    def test_rejects_unsafe_or_ambiguous_segments(self, user_id: str):
        assert is_safe_user_id(user_id) is False
