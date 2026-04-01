import threading

from kajson.class_registry import ClassRegistry
from kajson.class_registry_abstract import ClassRegistryAbstract
from kajson.kajson_manager import KajsonManager

from pipelex import log
from pipelex.hub import get_library_manager, set_current_library, teardown_current_library
from pipelex.libraries.library_crate import LibraryCrate

# Global dict mapping wf_library_id -> ClassRegistry for each active workflow.
# The Temporal data converter runs OUTSIDE the workflow coroutine's async context
# (during SDK activation processing), so ContextVar-based get_class_registry()
# returns the global registry. This dict lets the converter find the correct
# per-workflow registry by falling back to any active workflow's registry.
_workflow_registries: dict[str, ClassRegistry] = {}
_workflow_registries_lock = threading.Lock()


def get_workflow_registry(wf_library_id: str) -> ClassRegistry | None:
    """Get a workflow's ClassRegistry by its library_id."""
    return _workflow_registries.get(wf_library_id)


def get_any_workflow_registry() -> ClassRegistryAbstract | None:
    """Get any active workflow's ClassRegistry.

    Used by the data converter as a fallback when the ContextVar-based lookup
    returns the global registry. In the Temporal worker, there's typically one
    active workflow being processed at a time during activation.
    """
    with _workflow_registries_lock:
        if _workflow_registries:
            return next(iter(_workflow_registries.values()))
    return None


def setup_workflow_library(
    library_crate: LibraryCrate,
    workflow_id: str,
) -> str:
    """Set up a per-workflow library from a crate.

    Creates a scoped ClassRegistry pre-seeded from the global registry,
    opens a new library, attaches the registry, and loads the crate.

    Args:
        library_crate: The crate containing dynamic concepts, pipes, and domains
        workflow_id: The Temporal workflow ID (used to derive the library_id)

    Returns:
        The library_id for teardown
    """
    # 1. Create per-workflow ClassRegistry pre-seeded from global
    global_registry = KajsonManager.get_class_registry()
    workflow_registry = ClassRegistry()
    if isinstance(global_registry, ClassRegistry):
        workflow_registry.register_classes_dict(dict(global_registry.root))
    else:
        log.warning("Global registry is not a ClassRegistry, cannot pre-seed workflow registry")

    # 2. Open library, attach registry, load crate, cache, and register.
    # Wrapped in try/except to ensure all-or-nothing: if any step fails,
    # partial state is cleaned up before re-raising.
    library_manager = get_library_manager()
    wf_library_id = f"wf_{workflow_id}"

    try:
        _wf_library_id, wf_library = library_manager.open_library(library_id=wf_library_id)
        wf_library.set_class_registry(workflow_registry)
        set_current_library(library_id=wf_library_id)

        # 3. Load crate (registers dynamic classes into workflow_registry via hub.get_class_registry())
        library_manager.load_from_crate(library_id=wf_library_id, crate=library_crate)

        # 4. Cache the crate so get_crate(wf_library_id) can retrieve it later.
        # ContentGeneratorChild calls get_current_library_crate() to propagate the crate
        # to child workflows (WfMakeObject, etc.) via their assignment models.
        # We cache here (not in load_from_crate) because load_from_crate is also called
        # by load_from_blueprints, where caching would conflict with blueprint accumulation.
        library_manager.cache_crate(library_id=wf_library_id, crate=library_crate)

        # 5. Register the workflow's ClassRegistry in the global dict so the Temporal
        # data converter can find it during activation processing (where ContextVars
        # are not available).
        with _workflow_registries_lock:
            _workflow_registries[wf_library_id] = workflow_registry
    except BaseException:
        # Clean up partial setup so callers don't leak resources
        with _workflow_registries_lock:
            _workflow_registries.pop(wf_library_id, None)
        try:
            library_manager.teardown(library_id=wf_library_id)
        except Exception as teardown_exc:
            log.warning(f"Failed to clean up partial workflow library '{wf_library_id}': {teardown_exc}")
        teardown_current_library()
        raise

    return wf_library_id


def teardown_workflow_library(wf_library_id: str) -> None:
    """Tear down a per-workflow library.

    Removes the library from the manager and clears the async context.

    Args:
        wf_library_id: The library_id returned by setup_workflow_library
    """
    try:
        with _workflow_registries_lock:
            _workflow_registries.pop(wf_library_id, None)
        get_library_manager().teardown(library_id=wf_library_id)
    finally:
        teardown_current_library()
