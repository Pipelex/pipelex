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

    @abstractmethod
    def is_variable_present(self, *, name: str) -> bool:
        """Whether the context holds a value under this top-level name, an alias included; an absent optional input does not."""
