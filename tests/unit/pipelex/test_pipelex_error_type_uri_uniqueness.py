"""Class-name uniqueness guard for the ``PipelexError.type_uri()`` keyspace.

Every loaded ``PipelexError`` subclass whose ``type_uri`` is derived from its class name must produce
a unique one. A collision there would mean two distinct error classes kebab to the same documentation
page by accident — this catches class-name reuses at CI time, not at docs-build time.

A class that declares ``_declared_type_uri`` points at a page on purpose, usually the existing page of
the generic family it belongs to, so it may share that page with the family's own class. What it may
not do is point at a page that does not exist, which the second case checks.
"""

from pathlib import Path

from pipelex.errors.error_pages_generator import iter_pipelex_error_subclasses
from pipelex.urls import URLs

_TESTS_ROOT = next(parent for parent in Path(__file__).resolve().parents if parent.name == "tests")
_ERROR_PAGES_DIR = _TESTS_ROOT.parent / "docs" / "errors"


class TestPipelexErrorTypeUriUniqueness:
    def test_all_derived_type_uris_are_unique(self) -> None:
        """Every loaded ``PipelexError`` subclass that derives its ``type_uri`` produces a unique one."""
        seen: dict[str, str] = {}
        for cls in iter_pipelex_error_subclasses():
            if isinstance(cls.__dict__.get("_declared_type_uri"), str):
                continue
            uri = cls.type_uri()
            if uri in seen and seen[uri] != cls.__name__:
                msg = f"type_uri collision: {cls.__name__} and {seen[uri]} both produce {uri!r}"
                raise AssertionError(msg)
            seen[uri] = cls.__name__

    def test_every_declared_type_uri_under_the_error_docs_names_an_existing_page(self) -> None:
        """A declared URI that points into the error docs must land on a page that is there."""
        missing: list[str] = []
        for cls in iter_pipelex_error_subclasses():
            declared = cls.__dict__.get("_declared_type_uri")
            if not isinstance(declared, str) or not declared.startswith(f"{URLs.error_docs_base}/"):
                continue
            slug = declared.removeprefix(f"{URLs.error_docs_base}/").strip("/")
            if not (_ERROR_PAGES_DIR / f"{slug}.md").is_file():
                missing.append(f"{cls.__name__} -> {declared}")
        assert not missing, "declared type URIs pointing at no error page:\n" + "\n".join(missing)
