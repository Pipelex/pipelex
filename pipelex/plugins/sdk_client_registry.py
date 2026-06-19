from collections.abc import Callable
from typing import Any

from pydantic import Field, RootModel

from pipelex.plugins.model_handle import ModelHandle

SdkClientRegistryRoot = dict[str, Any]


class SdkClientRegistry(RootModel[SdkClientRegistryRoot]):
    root: SdkClientRegistryRoot = Field(default_factory=dict)

    def teardown(self):
        for sdk_instance in self.root.values():
            if hasattr(sdk_instance, "teardown"):
                sdk_instance.teardown()
        self.root = {}

    def get(self, model_handle: ModelHandle) -> Any | None:
        return self.root.get(model_handle.sdk_handle)

    def set(self, *, model_handle: ModelHandle, sdk_instance: Any) -> Any:
        self.root[model_handle.sdk_handle] = sdk_instance
        return sdk_instance

    def get_or_create(self, *, handle: ModelHandle, build: Callable[[], Any]) -> Any:
        """Return the cached SDK client for ``handle``, building and caching it on a miss.

        The DRY replacement for the ``get(...) or set(...)`` dance that used to be
        repeated in every dispatch arm. ``build`` is only called on a cache miss,
        so the heavy SDK client construction stays lazy.
        """
        existing = self.get(handle)
        if existing is not None:
            return existing
        return self.set(model_handle=handle, sdk_instance=build())
