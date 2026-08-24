"""Smoke tests for the per-class error documentation page generator."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_pages_generator import (
    _MACRO_SECTIONS,  # pyright: ignore[reportPrivateUsage]
    AUTHORED_MARKER,
    GENERATED_MARKER,
    INDEX_STEM,
    ErrorPagesReport,
    _force_load_all_error_modules,  # pyright: ignore[reportPrivateUsage]
    generate_error_pages,
    has_authored_marker,
    iter_pipelex_error_subclasses,
    page_slug,
)
from pipelex.tools.misc.string_utils import pascal_case_to_kebab

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _find_mkdocs_config() -> Path:
    """Walk up from this test module to the repo root holding ``mkdocs.yml``."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "mkdocs.yml"
        if candidate.is_file():
            return candidate
    msg = "mkdocs.yml not found in any parent of the test module"
    raise FileNotFoundError(msg)


class TestErrorPagesGenerator:
    def test_emits_one_page_per_loaded_subclass_plus_index_and_macros(self, tmp_path: Path) -> None:
        """Every subclass gets a per-class page; a landing ``index.md`` and the macro pages are emitted too."""
        report = generate_error_pages(output_dir=tmp_path)

        subclasses = list(iter_pipelex_error_subclasses())
        class_stems = {pascal_case_to_kebab(cls.__name__) for cls in subclasses}
        macro_stems = {slug for slug, _ in _MACRO_SECTIONS}

        emitted_paths = report.written + report.unchanged + report.preserved
        emitted_stems = {path.stem for path in emitted_paths}

        assert class_stems <= emitted_stems, "every per-class page must be emitted"
        assert INDEX_STEM in emitted_stems
        assert macro_stems <= emitted_stems, "every macro listing page must be emitted (all are non-empty in the full set)"
        assert report.removed == []
        assert report.total == len(emitted_stems)

        for stem in emitted_stems:
            page = tmp_path / f"{stem}.md"
            assert page.exists(), f"missing page for stem {stem!r}"
            assert GENERATED_MARKER in page.read_text(encoding="utf-8")

    def test_macro_pages_link_every_class(self, tmp_path: Path) -> None:
        """Every per-class page is reachable from exactly one macro listing page."""
        generate_error_pages(output_dir=tmp_path)
        macro_bodies = "".join(
            (tmp_path / f"{slug}.md").read_text(encoding="utf-8") for slug, _ in _MACRO_SECTIONS if (tmp_path / f"{slug}.md").exists()
        )
        for cls in iter_pipelex_error_subclasses():
            link_target = f"]({page_slug(cls)}.md)"
            assert link_target in macro_bodies, f"no macro page links {link_target!r}"

    def test_index_links_each_emitted_macro_page(self, tmp_path: Path) -> None:
        """The overview ``index.md`` links every macro listing page that was emitted."""
        generate_error_pages(output_dir=tmp_path)
        index_body = (tmp_path / f"{INDEX_STEM}.md").read_text(encoding="utf-8")
        for slug, _ in _MACRO_SECTIONS:
            if (tmp_path / f"{slug}.md").exists():
                assert f"]({slug}.md)" in index_body, f"index missing link to macro page {slug!r}"

    def test_macro_slugs_are_wired_into_mkdocs_nav(self) -> None:
        """Each generator macro slug must be wired into ``mkdocs.yml`` — as a nav entry and a
        ``not_in_nav`` re-include — so the hand-maintained nav can never drift from
        ``_MACRO_SECTIONS`` and break ``mkdocs build --strict`` on a missing or renamed page.
        """
        config_lines = [line.strip() for line in _find_mkdocs_config().read_text(encoding="utf-8").splitlines()]
        for slug, _ in _MACRO_SECTIONS:
            nav_suffix = f": errors/{slug}.md"
            assert any(line.endswith(nav_suffix) for line in config_lines), f"mkdocs.yml nav has no entry for macro page errors/{slug}.md"
            assert f"!errors/{slug}.md" in config_lines, f"mkdocs.yml not_in_nav is missing the re-include !errors/{slug}.md"

    def test_run_is_idempotent(self, tmp_path: Path) -> None:
        """Re-running the generator over its own output writes nothing — every page is byte-identical."""
        first = generate_error_pages(output_dir=tmp_path)
        assert first.unchanged == []
        assert first.preserved == []
        assert first.removed == []

        second = generate_error_pages(output_dir=tmp_path)
        assert second.written == []
        assert second.preserved == []
        assert second.removed == []
        assert len(second.unchanged) == first.total

    def test_authored_marker_preserves_hand_edited_page(self, tmp_path: Path) -> None:
        """A page bearing the standalone authored marker survives regeneration verbatim."""
        target_class = next(iter_pipelex_error_subclasses())
        slug = page_slug(target_class)
        page_path = tmp_path / f"{slug}.md"
        authored_body = f"{AUTHORED_MARKER}\n\n# Custom title\n\nMaintainer-curated content.\n"
        page_path.write_text(authored_body, encoding="utf-8")

        report = generate_error_pages(output_dir=tmp_path)

        assert page_path in report.preserved
        assert page_path not in report.written
        assert page_path.read_text(encoding="utf-8") == authored_body

    def test_authored_marker_detection_ignores_marker_inside_other_content(self) -> None:
        """The marker must appear as its own (stripped) line — substring matches don't count."""
        body_with_marker_in_prose = "<!-- pipelex:generated -->\n<!-- Add the `<!-- pipelex:authored -->` marker to claim this page -->\n"
        assert has_authored_marker(body_with_marker_in_prose) is False

        body_with_standalone_marker = f"some content\n{AUTHORED_MARKER}\nmore content\n"
        assert has_authored_marker(body_with_standalone_marker) is True

    def test_report_total_sums_four_populations(self) -> None:
        """``total`` should equal the sum of ``written`` + ``unchanged`` + ``preserved`` + ``removed``."""
        report = ErrorPagesReport(
            written=[Path("a.md"), Path("b.md")],
            unchanged=[Path("c.md")],
            preserved=[Path("d.md"), Path("e.md"), Path("f.md")],
            removed=[Path("g.md"), Path("h.md")],
        )
        assert report.total == 8

    def test_kebab_slug_collision_raises(self, tmp_path: Path) -> None:
        """Two classes that kebab to the same slug fail generation loudly."""

        class LLMError(PipelexError):
            pass

        class LlmError(PipelexError):
            pass

        with pytest.raises(RuntimeError, match="Kebab-slug collision on 'llm-error'"):
            generate_error_pages(output_dir=tmp_path, classes=[LLMError, LlmError])

    def test_reserved_slug_collision_raises(self, tmp_path: Path) -> None:
        """A class kebab-ing to a listing-page stem (a macro area, here ``platform-and-tooling``)
        fails loudly instead of having its per-class page silently overwritten by the listing page.
        """

        # Deliberately no `Error` suffix: the collision can only arise for a name that kebabs
        # onto a reserved listing-page stem, and an ``…Error`` name always kebabs to ``…-error``.
        class PlatformAndTooling(PipelexError):  # ruff: ignore[error-suffix-on-exception-name]
            pass

        with pytest.raises(RuntimeError, match="Reserved-slug collision on 'platform-and-tooling'"):
            generate_error_pages(output_dir=tmp_path, classes=[PlatformAndTooling])

    def test_orphan_generated_page_is_deleted(self, tmp_path: Path) -> None:
        """A generated page whose slug is no longer in target_classes is deleted and reported under ``removed``."""

        class FooError(PipelexError):
            pass

        first = generate_error_pages(output_dir=tmp_path, classes=[FooError])
        foo_page = tmp_path / f"{page_slug(FooError)}.md"
        assert foo_page in first.written
        assert foo_page.exists()

        # Re-run with an empty target set — FooError's page is now an orphan.
        second = generate_error_pages(output_dir=tmp_path, classes=[])
        assert foo_page in second.removed
        assert not foo_page.exists()

    def test_orphan_authored_page_is_preserved_not_deleted(self, tmp_path: Path) -> None:
        """A hand-authored page (no longer mapped to a target class) is preserved, not removed."""
        authored_page = tmp_path / "stale-but-authored.md"
        authored_body = f"{AUTHORED_MARKER}\n\n# Custom notes\n"
        authored_page.write_text(authored_body, encoding="utf-8")

        report = generate_error_pages(output_dir=tmp_path, classes=[])

        assert authored_page in report.preserved
        assert authored_page not in report.removed
        assert authored_page.read_text(encoding="utf-8") == authored_body

    def test_orphan_unmarked_file_is_left_alone(self, tmp_path: Path) -> None:
        """A file with neither marker is treated as out-of-scope and never touched."""
        unmarked_page = tmp_path / "random-note.md"
        unmarked_body = "# Random note\n\nNot ours to manage.\n"
        unmarked_page.write_text(unmarked_body, encoding="utf-8")

        report = generate_error_pages(output_dir=tmp_path, classes=[])

        assert unmarked_page not in report.removed
        assert unmarked_page not in report.preserved
        assert unmarked_page.read_text(encoding="utf-8") == unmarked_body

    def test_force_load_walk_continues_past_first_failure(self, mocker: MockerFixture) -> None:
        """Every per-module import failure is aggregated — the walk must NOT abort on the first one.

        Pins the multi-failure aggregation contract: the existing
        ``test_force_load_aggregates_non_import_error_failures`` only asserts
        the first module's name appears in the message, so a regression that
        re-raises on the first failure (instead of accumulating) would still
        pass. This test asserts at least two distinct dotted module names
        appear in the raised ``RuntimeError.args[0]``.
        """
        _force_load_all_error_modules.cache_clear()
        try:
            mocker.patch(
                "pipelex.errors.error_pages_generator.importlib.import_module",
                side_effect=NameError("boom"),
            )
            with pytest.raises(RuntimeError) as exc_info:
                _force_load_all_error_modules()
            message = str(exc_info.value)
            distinct_module_names = {line.strip(" -").split(":", 1)[0] for line in message.splitlines() if line.strip().startswith("- ")}
            assert len(distinct_module_names) >= 2, (
                f"expected at least 2 distinct walked dotted module names in the aggregated RuntimeError; "
                f"saw {len(distinct_module_names)}: {sorted(distinct_module_names)}"
            )
        finally:
            _force_load_all_error_modules.cache_clear()

    def test_force_load_aggregates_non_import_error_failures(self, mocker: MockerFixture) -> None:
        """A `NameError` (or any non-ImportError) raised during module init is aggregated, not propagated raw.

        Regression for greptile review: if a `*_exceptions.py` has a typo at module scope, its
        import raises `NameError` — not `ImportError`. The walk must still finish for every other
        module and surface the broken module's dotted name in the final `RuntimeError`.
        """
        _force_load_all_error_modules.cache_clear()
        try:
            mocker.patch(
                "pipelex.errors.error_pages_generator.importlib.import_module",
                side_effect=NameError("boom"),
            )
            with pytest.raises(RuntimeError, match="boom") as exc_info:
                _force_load_all_error_modules()
            message = str(exc_info.value)
            assert "pipelex.base_exceptions" in message, "RuntimeError should list at least one walked dotted module"
        finally:
            _force_load_all_error_modules.cache_clear()
