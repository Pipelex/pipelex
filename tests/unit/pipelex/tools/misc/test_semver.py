# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
import pytest
from semantic_version import SimpleSpec, Version  # type: ignore[import-untyped]

from pipelex.tools.misc.semver import (
    SemVerError,
    parse_constraint,
    parse_version,
    parse_version_tag,
    select_minimum_version,
    select_minimum_version_for_multiple_constraints,
    version_satisfies,
)


class TestSemver:
    """Tests for the semver constraint evaluation engine."""

    @pytest.mark.parametrize(
        "version_str",
        [
            "1.0.0",
            "0.1.0",
            "1.2.3-alpha",
            "1.2.3-alpha.1",
            "1.2.3+build",
            "1.2.3-beta.1+build.123",
        ],
    )
    def test_parse_version_valid(self, version_str: str) -> None:
        """Valid semver strings parse without error."""
        result = parse_version(version_str)
        assert isinstance(result, Version)

    @pytest.mark.parametrize(
        "version_str",
        [
            "abc",
            "",
            "1.0.0.0",
        ],
    )
    def test_parse_version_invalid(self, version_str: str) -> None:
        """Invalid semver strings raise SemVerError."""
        with pytest.raises(SemVerError):
            parse_version(version_str)

    def test_parse_version_strips_v_prefix(self) -> None:
        """A leading 'v' prefix is stripped before parsing."""
        result = parse_version("v1.2.3")
        assert result == Version("1.2.3")

    @pytest.mark.parametrize(
        ("lower", "higher"),
        [
            ("1.0.0", "2.0.0"),
            ("1.0.0", "1.1.0"),
            ("1.0.0", "1.0.1"),
            ("1.0.0-alpha", "1.0.0"),
            ("1.0.0-alpha", "1.0.0-beta"),
        ],
    )
    def test_version_comparison_ordering(self, lower: str, higher: str) -> None:
        """Versions compare in the correct semver order."""
        assert parse_version(lower) < parse_version(higher)

    @pytest.mark.parametrize(
        ("constraint_str", "version_str", "expected"),
        [
            ("^1.2.3", "1.2.3", True),
            ("^1.2.3", "1.9.9", True),
            ("^1.2.3", "2.0.0", False),
            ("^1.2.3", "1.2.2", False),
            ("^0.2.3", "0.2.3", True),
            ("^0.2.3", "0.2.9", True),
            ("^0.2.3", "0.3.0", False),
            ("^0.2.3", "0.2.2", False),
        ],
    )
    def test_version_satisfies_caret(self, constraint_str: str, version_str: str, expected: bool) -> None:
        """Caret constraints allow compatible updates within the same major (or minor for 0.x)."""
        constraint = parse_constraint(constraint_str)
        version = parse_version(version_str)
        assert version_satisfies(version, constraint) == expected

    @pytest.mark.parametrize(
        ("constraint_str", "version_str", "expected"),
        [
            ("~1.2.3", "1.2.3", True),
            ("~1.2.3", "1.2.9", True),
            ("~1.2.3", "1.3.0", False),
            ("~1.2.3", "1.2.2", False),
        ],
    )
    def test_version_satisfies_tilde(self, constraint_str: str, version_str: str, expected: bool) -> None:
        """Tilde constraints allow patch-level updates only."""
        constraint = parse_constraint(constraint_str)
        version = parse_version(version_str)
        assert version_satisfies(version, constraint) == expected

    @pytest.mark.parametrize(
        ("constraint_str", "version_str", "expected"),
        [
            (">=1.0.0", "1.0.0", True),
            (">=1.0.0", "0.9.9", False),
            (">1.0.0", "1.0.1", True),
            (">1.0.0", "1.0.0", False),
            ("<=2.0.0", "2.0.0", True),
            ("<=2.0.0", "2.0.1", False),
            ("<2.0.0", "1.9.9", True),
            ("<2.0.0", "2.0.0", False),
            ("==1.0.0", "1.0.0", True),
            ("==1.0.0", "1.0.1", False),
            ("!=1.0.0", "1.0.1", True),
            ("!=1.0.0", "1.0.0", False),
        ],
    )
    def test_version_satisfies_comparison_ops(self, constraint_str: str, version_str: str, expected: bool) -> None:
        """Comparison operators (>=, >, <=, <, ==, !=) work correctly."""
        constraint = parse_constraint(constraint_str)
        version = parse_version(version_str)
        assert version_satisfies(version, constraint) == expected

    @pytest.mark.parametrize(
        ("constraint_str", "version_str", "expected"),
        [
            ("*", "1.0.0", True),
            ("*", "99.99.99", True),
            ("==1.*", "1.0.0", True),
            ("==1.*", "1.9.9", True),
            ("==1.*", "2.0.0", False),
        ],
    )
    def test_version_satisfies_wildcard(self, constraint_str: str, version_str: str, expected: bool) -> None:
        """Wildcard constraints match any version (or within a major range)."""
        constraint = parse_constraint(constraint_str)
        version = parse_version(version_str)
        assert version_satisfies(version, constraint) == expected

    @pytest.mark.parametrize(
        ("constraint_str", "version_str", "expected"),
        [
            (">=1.0.0,<2.0.0", "1.5.0", True),
            (">=1.0.0,<2.0.0", "0.9.0", False),
            (">=1.0.0,<2.0.0", "2.0.0", False),
        ],
    )
    def test_version_satisfies_compound(self, constraint_str: str, version_str: str, expected: bool) -> None:
        """Compound constraints (AND of multiple sub-constraints) work correctly."""
        constraint = parse_constraint(constraint_str)
        version = parse_version(version_str)
        assert version_satisfies(version, constraint) == expected

    def test_version_satisfies_exact_no_operator(self) -> None:
        """A bare version string (no operator) means exact match."""
        constraint = parse_constraint("1.0.0")
        assert version_satisfies(parse_version("1.0.0"), constraint) is True
        assert version_satisfies(parse_version("1.0.1"), constraint) is False

    @pytest.mark.parametrize(
        ("tag", "expected_major", "expected_minor", "expected_patch"),
        [
            ("v1.2.3", 1, 2, 3),
            ("1.0.0", 1, 0, 0),
        ],
    )
    def test_parse_version_tag_valid(self, tag: str, expected_major: int, expected_minor: int, expected_patch: int) -> None:
        """Valid semver tags (with or without v prefix) parse to Version."""
        result = parse_version_tag(tag)
        assert result is not None
        assert result.major == expected_major
        assert result.minor == expected_minor
        assert result.patch == expected_patch

    @pytest.mark.parametrize(
        "tag",
        [
            "release-20240101",
            "latest",
        ],
    )
    def test_parse_version_tag_invalid(self, tag: str) -> None:
        """Non-semver tags return None."""
        assert parse_version_tag(tag) is None

    def test_select_minimum_version(self) -> None:
        """MVS returns the lowest version satisfying the constraint."""
        versions = [Version("1.0.0"), Version("1.1.0"), Version("1.2.0"), Version("2.0.0")]
        constraint = SimpleSpec("^1.0.0")
        result = select_minimum_version(versions, constraint)
        assert result == Version("1.0.0")

    def test_select_minimum_version_skips_non_matching(self) -> None:
        """MVS skips versions that don't satisfy the constraint."""
        versions = [Version("0.9.0"), Version("1.0.0"), Version("1.5.0")]
        constraint = SimpleSpec(">=1.0.0")
        result = select_minimum_version(versions, constraint)
        assert result == Version("1.0.0")

    def test_select_minimum_version_no_match(self) -> None:
        """MVS returns None when no version matches."""
        versions = [Version("1.0.0")]
        constraint = SimpleSpec("^2.0.0")
        result = select_minimum_version(versions, constraint)
        assert result is None

    def test_select_minimum_version_empty_list(self) -> None:
        """MVS returns None for an empty version list."""
        constraint = SimpleSpec("^1.0.0")
        result = select_minimum_version([], constraint)
        assert result is None

    def test_select_minimum_version_multiple_constraints(self) -> None:
        """Multi-constraint MVS returns the lowest version satisfying all constraints."""
        versions = [Version("1.0.0"), Version("1.2.0"), Version("2.0.0")]
        constraints = [SimpleSpec(">=1.0.0"), SimpleSpec(">=1.2.0")]
        result = select_minimum_version_for_multiple_constraints(versions, constraints)
        assert result == Version("1.2.0")

    def test_select_minimum_version_multiple_constraints_unsatisfiable(self) -> None:
        """Multi-constraint MVS returns None when constraints are unsatisfiable together."""
        versions = [Version("1.0.0"), Version("2.0.0")]
        constraints = [SimpleSpec(">=1.5.0"), SimpleSpec("<2.0.0")]
        result = select_minimum_version_for_multiple_constraints(versions, constraints)
        assert result is None
