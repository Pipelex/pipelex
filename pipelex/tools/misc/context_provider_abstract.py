from abc import ABC, abstractmethod
from typing import Any

from pipelex.system.exceptions import ToolException


class ContextProviderException(ToolException):
    def __init__(self, message: str, variable_name: str):
        super().__init__(message=message)
        self.variable_name = variable_name


class ContextProviderAbstract(ABC):
    """A ContextProvider provides context to templating engine. This interface is implemented by WorkingMemory.
    It exists to make these features available to lower level classes.
    """

    @abstractmethod
    def get_typed_object_or_attribute(self, name: str, wanted_type: type[Any] | None = None, accept_list: bool = False) -> Any:
        pass

    @abstractmethod
    def generate_context(self) -> dict[str, Any]:
        pass
