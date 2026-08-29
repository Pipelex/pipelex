"""Unit tests for the method reference grammar: `<address>[@<tag>]`."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pipelex.methods.exceptions import MethodRefParseError
from pipelex.methods.method_ref import MethodRef, looks_like_method_ref, parse_method_ref


class TestMethodRefGrammar:
    """Tests for parsing and detection of method references."""

    @pytest.mark.parametrize(
        ("ref", "expected_address", "expected_tag"),
        [
            ("github.com/Pipelex/methods/documents", "github.com/Pipelex/methods/documents", None),
            ("github.com/Pipelex/methods/documents@v0.2.0", "github.com/Pipelex/methods/documents", "v0.2.0"),
            ("github.com/acme/legal-tools", "github.com/acme/legal-tools", None),
            ("github.com/acme/legal-tools@1.0.0-rc.1", "github.com/acme/legal-tools", "1.0.0-rc.1"),
            ("github.com/org/repo@release/v1", "github.com/org/repo", "release/v1"),
            ("https://github.com/org/repo", "github.com/org/repo", None),
            ("https://github.com/org/repo/", "github.com/org/repo", None),
            ("https://github.com/org/repo.git", "github.com/org/repo", None),
            ("http://github.com/org/repo", "github.com/org/repo", None),
            ("https://github.com/org/repo@v1.2.3", "github.com/org/repo", "v1.2.3"),
            ("https://github.com/org/repo/tree/main/methods/documents", "github.com/org/repo/methods/documents", None),
            ("https://github.com/org/repo/blob/dev/pkg", "github.com/org/repo/pkg", None),
            ("github.com/org/repo/deep/nested/selector", "github.com/org/repo/deep/nested/selector", None),
        ],
    )
    def test_parse_valid(self, ref: str, expected_address: str, expected_tag: str | None) -> None:
        """Valid references parse into the normalized address and optional tag."""
        parsed = parse_method_ref(ref)
        assert parsed.address == expected_address
        assert parsed.tag == expected_tag

    @pytest.mark.parametrize(
        "ref",
        [
            "",
            "   ",
            "github.com",
            "github.com/only-owner",
            "gitlab.com/org/repo",
            "https://gitlab.com/org/repo",
            "example.io/pkg",
            "github.com/org/repo@",
            "github.com/org/re po",
            "github.com/org/repo@v1@v2",
        ],
    )
    def test_parse_invalid(self, ref: str) -> None:
        """Invalid references raise MethodRefParseError."""
        with pytest.raises(MethodRefParseError):
            parse_method_ref(ref)

    def test_parsed_ref_properties(self) -> None:
        """Owner, repo, selector, repo address, clone URL, and canonical string are derived."""
        parsed = parse_method_ref("github.com/Pipelex/methods/documents@v0.2.0")
        assert parsed.owner == "Pipelex"
        assert parsed.repo == "methods"
        assert parsed.selector == "documents"
        assert parsed.repo_address == "github.com/Pipelex/methods"
        assert parsed.clone_url == "https://github.com/Pipelex/methods.git"
        assert parsed.ref_str == "github.com/Pipelex/methods/documents@v0.2.0"

    def test_repo_root_ref_has_no_selector(self) -> None:
        """A repo-root reference has no selector and round-trips its address."""
        parsed = parse_method_ref("github.com/acme/legal-tools")
        assert parsed.selector is None
        assert parsed.repo_address == "github.com/acme/legal-tools"
        assert parsed.ref_str == "github.com/acme/legal-tools"

    @pytest.mark.parametrize(
        ("target", "expected"),
        [
            ("github.com/Pipelex/methods/documents", True),
            ("github.com/Pipelex/methods/documents@v0.2.0", True),
            ("https://github.com/org/repo", True),
            ("http://github.com/org/repo", True),
            ("my-method", False),
            ("./local/path", False),
            ("/absolute/path", False),
            ("methods/documents", False),
            ("https://gitlab.com/org/repo", False),
            ("", False),
        ],
    )
    def test_looks_like_method_ref(self, target: str, expected: bool) -> None:
        """Bare github.com addresses and GitHub URLs are detected; names and paths are not."""
        assert looks_like_method_ref(target) is expected

    def test_method_ref_is_frozen(self) -> None:
        """MethodRef is immutable."""
        parsed = MethodRef(address="github.com/org/repo", tag="v1.0.0")
        with pytest.raises(ValidationError, match="frozen"):
            parsed.tag = "v2.0.0"  # type: ignore[misc]  # pyright: ignore[reportAttributeAccessIssue]
