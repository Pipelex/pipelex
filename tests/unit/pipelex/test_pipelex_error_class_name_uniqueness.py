"""Class-name uniqueness guard for the ``error_type`` keyspace.

Every report carries ``error_type``, the class name verbatim, and consumers branch on it, so two distinct
``PipelexError`` subclasses sharing a name would be one error to every reader. The type URI no longer
derives from the class name (it is the page of the error's registry code), so the guard is on the name
itself, case-folded so that acronym-casing variants (``LLMError`` and ``LlmError``) collide here too.
"""

from pipelex.errors.error_class_discovery import iter_pipelex_error_subclasses


class TestPipelexErrorClassNameUniqueness:
    def test_all_error_class_names_are_unique(self) -> None:
        """Every loaded ``PipelexError`` subclass has a name no other one shares, ignoring case."""
        seen: dict[str, str] = {}
        for cls in iter_pipelex_error_subclasses():
            folded_name = cls.__name__.casefold()
            qualified_name = f"{cls.__module__}.{cls.__qualname__}"
            if folded_name in seen and seen[folded_name] != qualified_name:
                msg = f"error_type collision: {qualified_name} and {seen[folded_name]} share the name {cls.__name__!r}"
                raise AssertionError(msg)
            seen[folded_name] = qualified_name
