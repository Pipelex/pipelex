from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Protocol, Type


class TypedGetterAbstract(ABC):
    @abstractmethod
    def get_typed_object_or_attribute(self, name: str, wanted_type: Optional[Type[Any]] = None) -> Any:
        pass

    @abstractmethod
    def generate_context(self) -> Dict[str, Any]:
        pass
