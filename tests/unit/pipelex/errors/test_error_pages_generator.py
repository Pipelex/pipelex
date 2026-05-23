"""Smoke tests for the per-class error documentation page generator."""

from __future__ import annotations

from pathlib import Path

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_pages_generator import (
    AUTHORED_MARKER,
    GENERATED_MARKER,
    INDEX_STEM,
    ErrorPagesReport,
    generate_error_pages,
    has_authored_marker,
    iter_pipelex_error_subclasses,
    page_slug,
)
from pipelex.tools.misc.string_utils import pascal_case_to_kebab


class TestErrorPagesGenerator:
    def test_emits_one_page_per_loaded_subclass_plus_index(self, tmp_path: Path) -> None:
        """Every loaded ``PipelexError`` subclass gets a per-class page, plus a landing ``index.md``."""
        report = generate_error_pages(output_dir=tmp_path)

        subclasses = list(iter_pipelex_error_subclasses())
        expected_stems = {pascal_case_to_kebab(cls.__name__) for cls in subclasses} | {INDEX_STEM}

        assert report.total == len(expected_stems)
        emitted_paths = report.written + report.unchanged + report.preserved
        assert {path.stem for path in emitted_paths} == expected_stems

        for stem in expected_stems:
            page = tmp_path / f"{stem}.md"
            assert page.exists(), f"missing page for stem {stem!r}"
            content = page.read_text(encoding="utf-8")
            assert GENERATED_MARKER in content

    def test_index_page_links_every_class(self, tmp_path: Path) -> None:
        """The landing ``index.md`` lists each per-class page (link by kebab slug)."""
        generate_error_pages(output_dir=tmp_path)
        index_body = (tmp_path / f"{INDEX_STEM}.md").read_text(encoding="utf-8")
        for cls in iter_pipelex_error_subclasses():
            link_target = f"]({page_slug(cls)}.md)"
            assert link_target in index_body, f"index missing link {link_target!r}"

    def test_run_is_idempotent(self, tmp_path: Path) -> None:
        """Re-running the generator over its own output writes nothing — every page is byte-identical."""
        first = generate_error_pages(output_dir=tmp_path)
        assert first.unchanged == []
        assert first.preserved == []

        second = generate_error_pages(output_dir=tmp_path)
        assert second.written == []
        assert second.preserved == []
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
        body_with_marker_in_prose = "<!-- gstack:generated -->\n<!-- Add the `<!-- gstack:authored -->` marker to claim this page -->\n"
        assert has_authored_marker(body_with_marker_in_prose) is False

        body_with_standalone_marker = f"some content\n{AUTHORED_MARKER}\nmore content\n"
        assert has_authored_marker(body_with_standalone_marker) is True

    def test_report_total_sums_three_populations(self) -> None:
        """``total`` should equal the sum of ``written`` + ``unchanged`` + ``preserved``."""
        report = ErrorPagesReport(
            written=[Path("a.md"), Path("b.md")],
            unchanged=[Path("c.md")],
            preserved=[Path("d.md"), Path("e.md"), Path("f.md")],
        )
        assert report.total == 6

    def test_kebab_slug_collision_raises(self, tmp_path: Path) -> None:
        """Two classes that kebab to the same slug fail generation loudly."""

        class LLMError(PipelexError):
            pass

        class LlmError(PipelexError):
            pass

        with pytest.raises(RuntimeError, match="Kebab-slug collision on 'llm-error'"):
            generate_error_pages(output_dir=tmp_path, classes=[LLMError, LlmError])
