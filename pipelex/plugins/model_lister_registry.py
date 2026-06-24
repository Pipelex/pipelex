from collections.abc import Awaitable, Callable
from typing import TypeAlias

# The uniform model-listing callable. A backend plugin registers one of these per
# ``sdk`` it can enumerate models for, alongside its worker factory. Like
# ``MakeWorkerFn`` it is import-light to *reference* (a plain callable) and only
# imports its SDK lazily when *called*.
#
# Called by ``ModelLister.list_models`` as:
#     await lister(sdk=sdk, backend_name=backend_name, backend=backend, flat=flat, any_listed=any_listed)
ListModelsFn: TypeAlias = Callable[..., Awaitable[None]]


class ModelListerRegistry:
    """Read view over the model listers contributed by discovered plugins.

    Keyed by ``sdk``. Built once at boot from the registrar's accumulated listers
    and stored on the hub; ``ModelLister.list_models`` looks up its lister here
    instead of branching on a ``match`` over SDK strings.

    A lookup miss is a *soft* outcome — the SDK simply has no remote-listing
    capability — so the lookup is ``get_optional`` returning ``None`` rather than
    raising (mirroring ``OrchestratorRegistry``). The caller reports such an SDK as
    unsupported-for-listing instead of failing.
    """

    def __init__(self, listers: dict[str, ListModelsFn]):
        self._listers: dict[str, ListModelsFn] = dict(listers)

    def get_optional(self, *, sdk: str) -> ListModelsFn | None:
        return self._listers.get(sdk)

    def has(self, *, sdk: str) -> bool:
        return sdk in self._listers

    @property
    def sdks(self) -> list[str]:
        return list(self._listers)
