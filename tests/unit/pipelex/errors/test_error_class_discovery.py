from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pipelex.base_exceptions import PipelexError
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.errors.error_class_discovery import (
    _force_load_all_error_modules,  # pyright: ignore[reportPrivateUsage]
    iter_pipelex_error_subclasses,
)

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TestErrorClassDiscovery:
    def test_discovery_yields_the_root_and_a_subclass_of_a_deferred_module(self) -> None:
        """The root comes first, and a subclass defined in an ``exceptions.py`` module is found."""
        discovered = list(iter_pipelex_error_subclasses())
        assert discovered[0] is PipelexError
        assert BundleResourceNotNamedError in discovered

    def test_force_load_walk_continues_past_first_failure(self, mocker: MockerFixture) -> None:
        """Every per-module import failure is aggregated: the walk does not abort on the first one."""
        _force_load_all_error_modules.cache_clear()
        try:
            mocker.patch(
                "pipelex.errors.error_class_discovery.importlib.import_module",
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
        """A ``NameError`` raised while a module initializes is aggregated, not propagated raw."""
        _force_load_all_error_modules.cache_clear()
        try:
            mocker.patch(
                "pipelex.errors.error_class_discovery.importlib.import_module",
                side_effect=NameError("boom"),
            )
            with pytest.raises(RuntimeError, match="boom") as exc_info:
                _force_load_all_error_modules()
            message = str(exc_info.value)
            assert "pipelex.base_exceptions" in message, "RuntimeError should list at least one walked dotted module"
        finally:
            _force_load_all_error_modules.cache_clear()
