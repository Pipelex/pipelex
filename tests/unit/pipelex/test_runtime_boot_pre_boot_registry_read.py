"""A class-registry read before any boot must not starve the next boot's global registry.

``KajsonManager.get_class_registry()`` instantiates the singleton when none exists, around an empty
``ClassRegistry``. That read is one call away from any pre-boot code: the scoped accessor
``pipelex.runtime_hub.get_class_registry`` falls back to it when no library is pinned, and
``LibraryManager.open_library`` seeds every library's registry from it. ``KajsonManager`` is a
``MetaSingleton``, so the boot's own ``KajsonManager(class_registry=…)`` would hand that pre-boot
manager back and discard the boot's registry — the core models then land where nothing resolves,
while the boot still reports ready. The boot drops any pre-boot manager before constructing its own.
"""

from kajson.kajson_manager import KajsonManager

from pipelex.pipelex import Pipelex
from pipelex.runtime_hub import get_class_registry
from pipelex.system.runtime import IntegrationMode, runtime_manager


def _test_integration_mode() -> IntegrationMode:
    """The boot mode the session conftest uses, so a re-boot here matches the one it replaces."""
    return IntegrationMode.CI if runtime_manager.is_ci_testing else IntegrationMode.PYTEST


class TestPreBootRegistryRead:
    def test_a_pre_boot_registry_read_does_not_starve_the_next_boot(self) -> None:
        Pipelex.teardown_if_needed()
        try:
            # The pre-boot read, through the same accessor any pre-boot caller would use.
            pre_boot_registry = get_class_registry()
            assert not pre_boot_registry.has_class(name="TextContent"), "no boot has registered the core models yet"
            assert KajsonManager.get_class_registry() is pre_boot_registry, "the read instantiated the singleton"

            pipelex = Pipelex.make(integration_mode=_test_integration_mode())

            served_registry = KajsonManager.get_class_registry()
            assert served_registry is pipelex.class_registry, "the boot must serve its own registry, not the pre-boot one"
            assert served_registry.has_class(name="TextContent")
            assert get_class_registry() is served_registry
        finally:
            # Restore what the module fixture set up, so its teardown is sane.
            Pipelex.teardown_if_needed()
            Pipelex.make(integration_mode=_test_integration_mode())
