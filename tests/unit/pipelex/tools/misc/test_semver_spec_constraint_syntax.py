# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""The MTHDS standard's "Version Constraint Syntax" table, exercised row by row.

That table in `mthds/docs/spec/manifest-format.md` is the contract `parse_constraint`
implements, so it gets a module of its own rather than riding along in the wrapper's unit
tests. Its compound row is written `>=1.0.0, <2.0.0` — with the space — and that row was
the one form never exercised: `SimpleSpec` splits on the comma without stripping, so the
leading space of the second clause made the whole constraint invalid.
"""

import pytest

from pipelex.tools.misc.semver import SemVerError, parse_constraint, parse_version, version_satisfies


class TestSpecVersionConstraintSyntax:
    """Every row of the table, as written there, plus the whitespace equivalences it implies."""

    @pytest.mark.parametrize(
        ("constraint", "satisfying", "unsatisfying"),
        [
            ("1.0.0", "1.0.0", "1.5.0"),
            ("^1.0.0", "1.5.0", "2.0.0"),
            ("~1.0.0", "1.0.0", "1.5.0"),
            (">=1.0.0", "2.0.0", "0.9.0"),
            ("<2.0.0", "1.5.0", "2.0.0"),
            (">1.0.0", "1.5.0", "1.0.0"),
            ("<=2.0.0", "2.0.0", "2.0.1"),
            ("==1.0.0", "1.0.0", "1.5.0"),
            ("!=1.0.0", "1.5.0", "1.0.0"),
            (">=1.0.0, <2.0.0", "1.5.0", "2.0.0"),
            ("*", "1.5.0", None),
            ("1.*", "1.5.0", "2.0.0"),
            ("1.0.*", "1.0.9", "1.5.0"),
            ("1.0", "1.0.9", "1.5.0"),
        ],
    )
    def test_every_documented_form_parses_and_evaluates(self, constraint: str, satisfying: str, unsatisfying: str | None) -> None:
        parsed = parse_constraint(constraint)
        assert version_satisfies(parse_version(satisfying), constraint=parsed)
        if unsatisfying is not None:
            assert not version_satisfies(parse_version(unsatisfying), constraint=parsed)

    @pytest.mark.parametrize(
        ("spaced", "tight"),
        [
            (">=1.0.0, <2.0.0", ">=1.0.0,<2.0.0"),
            (">=1.0.0 , <2.0.0", ">=1.0.0,<2.0.0"),
            ("  ^1.0.0  ", "^1.0.0"),
        ],
    )
    def test_whitespace_around_clauses_is_not_part_of_the_constraint(self, spaced: str, tight: str) -> None:
        """The two spellings are one constraint in the grammar, so they must agree on every version."""
        spaced_spec = parse_constraint(spaced)
        tight_spec = parse_constraint(tight)
        for version_str in ("0.9.0", "1.0.0", "1.5.0", "2.0.0"):
            version = parse_version(version_str)
            assert version_satisfies(version, constraint=spaced_spec) == version_satisfies(version, constraint=tight_spec)

    def test_an_empty_clause_is_still_a_parse_error(self) -> None:
        """Stripping normalizes whitespace; it must not silently repair a malformed compound."""
        with pytest.raises(SemVerError):
            parse_constraint(">=1.0.0,,<2.0.0")
