"""Class-name uniqueness guard for the ``PipelexError.type_uri()`` keyspace.

Every loaded ``PipelexError`` subclass whose ``type_uri`` is derived from its class name must produce
a unique one. A collision there would mean two distinct error classes kebab to the same URI by
accident — this catches class-name reuses at CI time. A class that declares ``_declared_type_uri``
shares a URI on purpose, so it is left out.
"""

from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses


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
