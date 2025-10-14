from abc import ABC, abstractmethod
from typing import Any

from pipelex.system.exceptions import ToolException


class ContextProviderException(ToolException):
    def __init__(self, variable_name: str, message: str, *args: object, **kwargs: object) -> None:
        self.variable_name = variable_name
        super().__init__(message, *args, **kwargs)


class ContextProviderAbstract(ABC):
    """A ContextProvider provides context to templating engine. This interface is implemented by WorkingMemory.
    It exists to make these features available to lower level classes.
    """

    @abstractmethod
    def get_typed_object_or_attribute(self, name: str, wanted_type: type[Any] | None = None) -> Any:
        pass

    @abstractmethod
    def generate_context(self) -> dict[str, Any]:
        pass
