from abc import ABC, abstractmethod
from typing import Any


class ContextProviderAbstract(ABC):
    """A ContextProvider provides context to templating engine. This interface is implemented by WorkingMemory.
    It exists to make these features available to lower level classes.
    """

    @abstractmethod
    def get_typed_object_or_attribute(self, name: str, *, wanted_type: type[Any] | None = None, accept_list: bool = False) -> Any:
        pass

    @abstractmethod
    def generate_context(self) -> dict[str, Any]:
        pass
