"""Unit tests for the auto-fix surface of the keyword-only guard (`fix_source` / `fix_all_violations`)."""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from pipelex.cli.dev_cli.commands.keyword_only_guard import (
    Violation,
    find_violations_in_source,
    fix_all_violations,
    fix_source,
)

if TYPE_CHECKING:
    from pathlib import Path


def _fix(
    source: str, *, module_qname: str = "pipelex.sample.module", relative_path: str = "pipelex/sample/module.py"
) -> tuple[str, list[Violation], list[Violation]]:
    """Run the auto-fixer over an inline snippet, returning (new_source, fixed, unfixable)."""
    return fix_source(textwrap.dedent(source), module_qname=module_qname, relative_path=relative_path)


def _names(violations: list[Violation]) -> list[str]:
    return [violation.qualified_name for violation in violations]


def _is_compliant(source: str) -> bool:
    """Whether a (rewritten) source has no remaining violations."""
    return find_violations_in_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py") == []


class TestKeywordOnlyGuardFix:
    def test_simple_function_gets_bare_star(self) -> None:
        """The `*` lands as far left as possible, making every parameter keyword-only."""
        new_source, fixed, unfixable = _fix(
            """
            def f(a, b):
                return a
            """
        )
        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert "def f(*, a, b):" in new_source
        assert _is_compliant(new_source)

    def test_method_star_lands_right_after_self(self) -> None:
        """`self` stays positional; the `*` lands right after it, making every other param keyword-only."""
        new_source, fixed, unfixable = _fix(
            """
            class C:
                def m(self, a, b):
                    return a
            """
        )
        assert _names(fixed) == ["C.m"]
        assert unfixable == []
        assert "def m(self, *, a, b):" in new_source
        assert _is_compliant(new_source)

    def test_classmethod_cls_dropped(self) -> None:
        """`cls` stays positional; the `*` lands right after it."""
        new_source, fixed, unfixable = _fix(
            """
            class C:
                @classmethod
                def make(cls, source, target):
                    return source
            """
        )
        assert _names(fixed) == ["C.make"]
        assert unfixable == []
        assert "def make(cls, *, source, target):" in new_source
        assert _is_compliant(new_source)

    def test_single_defaulted_option_named(self) -> None:
        """A lone subject plus an option: the `*` goes to the far left, making both keyword-only."""
        new_source, fixed, unfixable = _fix(
            """
            def truncate(text, max_length=80):
                return text
            """
        )
        assert _names(fixed) == ["truncate"]
        assert unfixable == []
        assert "def truncate(*, text, max_length=80):" in new_source
        assert _is_compliant(new_source)

    def test_annotations_and_default_preserved(self) -> None:
        """The `*` is inserted before the first parameter name, leaving annotations/defaults intact."""
        new_source, fixed, unfixable = _fix(
            """
            def f(a: int, b: str = "x") -> int:
                return a
            """
        )
        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert 'def f(*, a: int, b: str = "x") -> int:' in new_source
        assert _is_compliant(new_source)

    def test_multiline_signature_fixed_and_compliant(self) -> None:
        """A signature spread across lines is fixed on the target parameter's own line."""
        new_source, fixed, unfixable = _fix(
            """
            def f(
                a,
                b,
            ):
                return a
            """
        )
        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert _is_compliant(new_source)

    def test_two_violations_in_one_source_both_fixed(self) -> None:
        new_source, fixed, unfixable = _fix(
            """
            def f(a, b):
                return a

            def h(x, y, z):
                return x
            """
        )
        assert _names(fixed) == ["f", "h"]
        assert unfixable == []
        assert "def f(*, a, b):" in new_source
        assert "def h(*, x, y, z):" in new_source
        assert _is_compliant(new_source)

    def test_compliant_source_unchanged(self) -> None:
        source = textwrap.dedent(
            """
            def g(subject, *, opt):
                return opt
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert (fixed, unfixable) == ([], [])
        assert new_source == source

    def test_lone_subject_unchanged(self) -> None:
        source = textwrap.dedent(
            """
            def render(node):
                return node
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert (fixed, unfixable) == ([], [])
        assert new_source == source

    def test_varargs_reported_unfixable_and_unchanged(self) -> None:
        """A `*args` signature cannot take a bare `*` — reported for a manual fix, source untouched."""
        source = textwrap.dedent(
            """
            def f(a, b, *args):
                return a
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert fixed == []
        assert _names(unfixable) == ["f"]
        assert new_source == source

    def test_existing_keyword_only_section_reported_unfixable(self) -> None:
        """A signature that already has a bare `*` (but a positional `b` before it) needs a manual merge."""
        source = textwrap.dedent(
            """
            def f(a, b, *, c):
                return a
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert fixed == []
        assert _names(unfixable) == ["f"]
        assert new_source == source

    def test_positional_only_subject_fixed_after_slash(self) -> None:
        """A single positional-only subject (before `/`) stays positional; the `*` goes right after the `/`."""
        new_source, fixed, unfixable = _fix(
            """
            def f(a, /, b, c):
                return a
            """
        )
        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert "def f(a, /, *, b, c):" in new_source
        assert _is_compliant(new_source)

    def test_multiple_positional_only_reported_unfixable(self) -> None:
        """Two+ positional-only params can't be made keyword-only by a bare `*` (it can't precede `/`) — manual fix."""
        source = textwrap.dedent(
            """
            def f(a, b, /, c):
                return a
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert fixed == []
        assert _names(unfixable) == ["f"]
        assert new_source == source

    def test_carveouts_are_never_touched(self) -> None:
        """Dunders, @override, pydantic validators and the escape hatch are not violations, so the fixer leaves them be."""
        source = textwrap.dedent(
            """
            class Box:
                def __setitem__(self, key, value):
                    ...

                @override
                def _store(self, data, key, content_type):
                    ...

                @field_validator("name", mode="before")
                def normalize(cls, value, info):
                    ...

            def safe(spec, dry_run):  # kw-only: ignore
                ...
            """
        )
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert (fixed, unfixable) == ([], [])
        assert new_source == source

    def test_escape_hatch_carveout_survives_form_feed_in_fix_path(self) -> None:
        r"""A `# kw-only: ignore` def must NOT be modified by the fixer, even with a form-feed earlier in the file.

        The escape hatch is the one carve-out that reads source text (`_def_line_has_escape_hatch`), so it is
        the carve-out at risk if `ast`-line indexing diverges from `str.splitlines()` (the F1/F2 bug). This pins
        that the fixer rewrites only the genuine violation and leaves the suppressed def byte-for-byte intact —
        a regression guard against reverting the tokenizer-accurate line split.
        """
        suppressed = "def suppressed(spec, dry_run):  # kw-only: ignore"
        source = f'BANNER = "page1\x0cpage2"\n{suppressed}\n    return spec\n\ndef real(alpha, beta):\n    return alpha\n'
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert _names(fixed) == ["real"]
        assert unfixable == []
        assert suppressed in new_source  # the escape-hatched def is untouched
        assert "def real(*, alpha, beta):" in new_source  # only the genuine violation is fixed
        assert _is_compliant(new_source)

    def test_fix_is_idempotent(self) -> None:
        """Re-fixing an already-fixed source produces no further change."""
        once, fixed, unfixable = _fix(
            """
            def f(a, b, c):
                return a
            """
        )
        assert _names(fixed) == ["f"]
        assert unfixable == []
        twice, fixed_again, unfixable_again = fix_source(once, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert (fixed_again, unfixable_again) == ([], [])
        assert twice == once

    def test_form_feed_in_string_neither_corrupts_nor_misreports(self) -> None:
        r"""A form-feed (\x0c) in a string literal before a violation must not derail line indexing.

        ``str.splitlines()`` splits on ``\x0c`` (and other exotic whitespace) but ``ast`` line numbers
        count only ``\n``/``\r``/``\r\n``. The old splitlines-based indexing landed the inserted ``*``
        on the wrong physical line — here it silently injects it INTO the triple-quoted string (which still
        re-parses) while leaving the real violation untouched and wrongly reporting it as fixed. The fix
        must insert the ``*`` into the def and leave the string byte-for-byte intact.
        """
        literal = '"""\naaaa\x0cbbbb\nxxxxxxxxxxxxxxxxxxxx"""'
        source = f"page = {literal}\ndef f(a, b):\n    return a\n"
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert "def f(*, a, b):" in new_source
        assert literal in new_source  # the string literal is untouched — no stray `*, ` injected into it
        assert _is_compliant(new_source)

    def test_crlf_line_endings_preserved_and_fixed(self) -> None:
        r"""A CRLF (\r\n) file is fixed on the right line with its line endings preserved byte-for-byte.

        ``_LINE_BREAK_RE`` matches ``\r\n``/``\r``/``\n`` and the capturing split rebuilds the file exactly;
        this pins the CRLF half of that regex (the form-feed tests above cover the ``splitlines()``-divergence
        half). A regression that broke CRLF reconstruction would corrupt every Windows-authored file the fixer
        touches — most dangerously by emitting bare ``\n`` where the source had ``\r\n``.
        """
        source = "X = 1\r\ndef f(a, b):\r\n    return a\r\n"
        new_source, fixed, unfixable = fix_source(source, module_qname="pipelex.sample.module", relative_path="pipelex/sample/module.py")
        assert _names(fixed) == ["f"]
        assert unfixable == []
        # The `*` lands on the def line and every CRLF separator is preserved byte-for-byte.
        assert new_source == "X = 1\r\ndef f(*, a, b):\r\n    return a\r\n"
        # No bare `\n` was introduced: every `\n` is still part of a `\r\n`.
        assert new_source.count("\n") == new_source.count("\r\n")
        assert _is_compliant(new_source)

    def test_fix_all_violations_rewrites_in_place(self, tmp_path: Path) -> None:
        """The filesystem entrypoint rewrites only the offending file and reports the fix."""
        sample = tmp_path / "pipelex" / "sample"
        sample.mkdir(parents=True)
        bad = sample / "bad.py"
        good = sample / "good.py"
        good_text = "def g(subject, *, opt):\n    return opt\n"
        bad.write_text("def f(a, b):\n    return a\n", encoding="utf-8")
        good.write_text(good_text, encoding="utf-8")

        fixed, unfixable = fix_all_violations(tmp_path / "pipelex")

        assert _names(fixed) == ["f"]
        assert unfixable == []
        assert "def f(*, a, b):" in bad.read_text(encoding="utf-8")
        assert good.read_text(encoding="utf-8") == good_text  # compliant file left byte-for-byte untouched
