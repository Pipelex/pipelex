from unittest.mock import patch

from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.interpreter_hub import clear_current_library, get_library_manager, set_current_library
from pipelex.libraries.library_factory import LibraryFactory
from pipelex.runtime_hub import get_class_registry


class ScopedModel(BaseModel):
    scoped_field: str


class TestHubClassRegistry:
    def test_get_class_registry_without_library_id_returns_global(self) -> None:
        """Without library_id set, hub returns the global KajsonManager registry."""
        result = get_class_registry()
        assert result is KajsonManager.get_class_registry()

    def test_get_class_registry_with_library_id_returns_library_registry(self) -> None:
        """When _library_id is set and the library has a ClassRegistry, hub returns it."""
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()

        workflow_registry = ClassRegistry()
        workflow_registry.register_class(ScopedModel)
        library.set_class_registry(workflow_registry)

        set_current_library(library_id=library_id)
        try:
            result = get_class_registry()
            assert result is workflow_registry
            assert result.has_class(name="ScopedModel")
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)

    def test_an_opened_library_gets_its_own_registry_seeded_from_the_global_one(self) -> None:
        """open_library attaches a per-library registry — scoping is structural, never opt-in.

        Before this was the default, a library that carried no registry resolved through to the
        process-global one, which let two libraries share a single ``domain__Concept`` slot and
        disclose one bundle's generated structure class to another.
        """
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        global_registry = KajsonManager.get_class_registry()

        library_registry = library.get_class_registry()
        assert library_registry is not None
        assert library_registry is not global_registry
        assert set(global_registry.get_classes_dict()) <= set(library_registry.get_classes_dict())

        set_current_library(library_id=library_id)
        try:
            assert get_class_registry() is library_registry
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)

    def test_opening_a_library_against_an_empty_global_registry_still_yields_one(self) -> None:
        """Seeding must survive an empty process-global registry.

        kajson's ``register_classes_dict`` names the single class it logs by indexing into the
        values, so handing it an empty dict raises ``IndexError`` rather than registering nothing.
        The global registry genuinely is empty between a teardown and the next boot, and a library
        opened there must come out carrying its own empty registry instead of failing to open.
        """
        library_manager = get_library_manager()
        with patch.object(KajsonManager, "get_class_registry", return_value=ClassRegistry()):
            library_id, library = library_manager.open_library()
        try:
            library_registry = library.get_class_registry()
            assert library_registry is not None
            assert library_registry.get_classes_dict() == {}
        finally:
            library_manager.teardown(library_id=library_id)

    def test_get_class_registry_with_unknown_library_id_falls_back_to_global(self) -> None:
        """_library_id pinned to a library the manager does not hold -> falls back to global."""
        set_current_library(library_id="no-such-library")
        try:
            result = get_class_registry()
            assert result is KajsonManager.get_class_registry()
        finally:
            clear_current_library()

    def test_library_class_registry_not_in_model_dump(self) -> None:
        """Library._class_registry (PrivateAttr) is not included in model_dump() output."""
        library = LibraryFactory.make_empty()
        registry = ClassRegistry()
        library.set_class_registry(registry)

        dump = library.model_dump()
        assert "_class_registry" not in dump
        assert "class_registry" not in dump

    def test_library_class_registry_gc_with_teardown(self) -> None:
        """When a library is torn down, its ClassRegistry is released."""
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()

        workflow_registry = ClassRegistry()
        workflow_registry.register_class(ScopedModel)
        library.set_class_registry(workflow_registry)

        set_current_library(library_id=library_id)
        assert get_class_registry().has_class(name="ScopedModel")

        clear_current_library()
        library_manager.teardown(library_id=library_id)

        # After teardown, hub falls back to global (which doesn't have ScopedModel)
        global_registry = get_class_registry()
        assert not global_registry.has_class(name="ScopedModel")
