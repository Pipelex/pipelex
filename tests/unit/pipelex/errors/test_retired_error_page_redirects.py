"""The static redirects of the retired per-class error pages follow each class's code."""

from __future__ import annotations

from difflib import unified_diff
from pathlib import Path

from mthds.protocol.problem.registry import CoreCode

import pipelex
from pipelex.base_exceptions import PipelexError
from pipelex.errors.error_code_declaration import ABSTRACT_ERROR, ErrorCodeSet, InheritsCause
from pipelex.errors.registry.pipelex_codes import PipelexErrorCode
from pipelex.errors.retired_error_pages import ERROR_CODES_INDEX_PAGE, render_retired_error_page_redirects, retired_page_names, retired_page_target

_REPO_ROOT: Path = Path(pipelex.__file__).resolve().parent.parent
_MKDOCS_FILE: Path = _REPO_ROOT / "mkdocs.yml"


class _CoreCodedError(PipelexError):
    error_code = CoreCode.MODEL_UNKNOWN


class _PipelexCodedSetError(PipelexError):
    error_code = ErrorCodeSet(default=PipelexErrorCode.CONFIG_SYNTAX, others=(PipelexErrorCode.CONFIG_INVALID,))


class _WrapperError(PipelexError):
    error_code = InheritsCause(fallback=CoreCode.PIPE_INPUT_UNRESOLVED)


class _BaseError(PipelexError):
    error_code = ABSTRACT_ERROR


class TestRetiredErrorPageRedirects:
    def test_the_block_records_the_retired_pages(self) -> None:
        names = retired_page_names(mkdocs_text=_MKDOCS_FILE.read_text(encoding="utf-8"))
        assert "pipelex-config-error" in names
        assert len(names) == len(set(names)), "A retired page is listed twice"

    def test_targets_follow_the_class_code(self) -> None:
        classes_by_kebab: dict[str, type[PipelexError]] = {
            "core-coded-error": _CoreCodedError,
            "pipelex-coded-set-error": _PipelexCodedSetError,
            "wrapper-error": _WrapperError,
            "base-error": _BaseError,
        }
        assert retired_page_target(kebab_name="core-coded-error", classes_by_kebab=classes_by_kebab) == "https://mthds.ai/errors/model.unknown"
        assert retired_page_target(kebab_name="pipelex-coded-set-error", classes_by_kebab=classes_by_kebab) == "errors/pipelex/config/syntax.md"
        assert retired_page_target(kebab_name="wrapper-error", classes_by_kebab=classes_by_kebab) == "https://mthds.ai/errors/pipe.input_unresolved"
        assert retired_page_target(kebab_name="base-error", classes_by_kebab=classes_by_kebab) == ERROR_CODES_INDEX_PAGE
        assert retired_page_target(kebab_name="gone-error", classes_by_kebab=classes_by_kebab) == ERROR_CODES_INDEX_PAGE

    def test_every_pipelex_target_is_a_generated_page(self) -> None:
        for line in _MKDOCS_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped.startswith("'errors/") or "': 'errors/" not in stripped:
                continue
            target = stripped.split("': '")[1].rstrip("'")
            assert (_REPO_ROOT / "docs" / target).is_file(), f"The redirect {stripped} names a page that does not exist"

    def test_committed_redirects_match_the_classes(self) -> None:
        existing = _MKDOCS_FILE.read_text(encoding="utf-8")
        expected = render_retired_error_page_redirects(mkdocs_text=existing)
        if existing == expected:
            return
        diff = unified_diff(
            existing.splitlines(), expected.splitlines(), fromfile="mkdocs.yml (on disk)", tofile="rendered from the classes", lineterm=""
        )
        lines = [
            "The redirects of the retired error class pages in mkdocs.yml do not follow the classes' codes; run `make gei`.",
            "",
            *diff,
        ]
        raise AssertionError("\n".join(lines))
