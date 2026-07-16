"""Class-name uniqueness guard for the ``PipelexError.type_uri()`` keyspace.

Every loaded ``PipelexError`` subclass must produce a unique ``type_uri``. A
collision would mean two distinct error classes point at the same documentation
page — catches future class-name reuses at CI time, not at docs-build time.
"""

from pipelex.errors.error_pages_generator import iter_pipelex_error_subclasses


class TestPipelexErrorTypeUriUniqueness:
    def test_all_pipelex_error_subclasses_have_unique_type_uris(self) -> None:
        """Every loaded ``PipelexError`` subclass produces a unique ``type_uri``."""
        seen: dict[str, str] = {}
        for cls in iter_pipelex_error_subclasses():
            uri = cls.type_uri()
            if uri in seen and seen[uri] != cls.__name__:
                msg = f"type_uri collision: {cls.__name__} and {seen[uri]} both produce {uri!r}"
                raise AssertionError(msg)
            seen[uri] = cls.__name__
