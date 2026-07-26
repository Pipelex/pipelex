from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel

from pipelex.libraries.library_factory import LibraryFactory
from pipelex.method_hub import clear_current_library, get_library_manager, set_current_library
from pipelex.service_hub import get_class_registry


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

    def test_get_class_registry_library_without_registry_falls_back_to_global(self) -> None:
        """_library_id set but library has no _class_registry -> falls back to global."""
        library_manager = get_library_manager()
        library_id, _library = library_manager.open_library()
        # Don't set a class_registry on the library

        set_current_library(library_id=library_id)
        try:
            result = get_class_registry()
            assert result is KajsonManager.get_class_registry()
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)

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
