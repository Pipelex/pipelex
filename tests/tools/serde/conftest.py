# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from datetime import datetime
from typing import Any, ClassVar, Dict, List, Tuple, TypeVar

from pydantic import BaseModel, Field, RootModel
from typing_extensions import override

from pipelex import log

BaseModelType = TypeVar("BaseModelType", bound=BaseModel)


class Number(BaseModel):
    value: int = Field(default=42, ge="10")


class ClassWithTrickyTypes:
    def __init__(self, data: Dict[str, Any]):
        self.created_at = data["created_at"]
        self.updated_at = data["updated_at"]
        self.my_number = data["my_number"]

    def __json_encode__(self):
        the_dict = self.__dict__.copy()
        the_dict.pop("__class__", None)
        the_dict.pop("__module__", None)
        return the_dict

    @classmethod
    def __json_decode__(cls, data: Dict[str, Any]):
        return cls(data)

    @override
    def __eq__(self, other: Any) -> bool:
        log.debug(f"Comparing {self} with {other}, i.e. {self.__dict__} with {other.__dict__}")
        if self.__dict__ == other.__dict__:
            return True
        return False


class PydanticWithTrickyTypes(BaseModel):
    created_at: datetime
    updated_at: datetime
    my_number: Number


class SubModel(BaseModel):
    int_value: int


class SubClass1(SubModel):
    other_value_1: str


class SubClass2(SubModel):
    other_value_2: float


class ModelToTweak(BaseModel):
    name: str


class PydanticWithTrickySubClasses(BaseModel):
    name: str
    sub_model: SubModel
    sub_model_list: List[SubModel]


obj_pydantic_tricky_sub_classes = PydanticWithTrickySubClasses(
    name="Original",
    sub_model=SubClass1(int_value=42, other_value_1="One"),
    sub_model_list=[
        SubClass1(int_value=-43, other_value_1="One"),
        SubClass2(int_value=144, other_value_2=2.0),
    ],
)

obj_pydantic_tricky_types = PydanticWithTrickyTypes(
    created_at=datetime(2023, 1, 1, 12, 0, 0),
    updated_at=datetime(2023, 1, 2, 12, 13, 25),
    my_number=Number(value=42),
)


obj_pydantic_tricky_types_json_str4 = """{
    "created_at": {
        "datetime": "2023-01-01 12:00:00.000000",
        "tzinfo": null,
        "__class__": "datetime",
        "__module__": "datetime"
    },
    "updated_at": {
        "datetime": "2023-01-02 12:13:25.000000",
        "tzinfo": null,
        "__class__": "datetime",
        "__module__": "datetime"
    },
    "my_number": {
        "value": 42,
        "__class__": "Number",
        "__module__": "tests.tools.serde.conftest"
    },
    "__class__": "PydanticWithTrickyTypes",
    "__module__": "tests.tools.serde.conftest"
}"""

obj_pydantic_tricky_types_dict = {
    "created_at": "2023-01-01T12:00:00",
    "updated_at": "2023-01-02T12:13:25",
    "my_number": {"value": 42},
}
obj_pydantic_tricky_types_dict_typed: Dict[str, Any] = {
    "created_at": datetime(2023, 1, 1, 12, 0),
    "updated_at": datetime(2023, 1, 2, 12, 13, 25),
    "my_number": {"value": 42},
}

obj_pydantic_tricky_types_json_str4_with_validation_error = """{
    "created_at": {
        "datetime": "2023-01-01 12:00:00.000000",
        "tzinfo": null,
        "__class__": "datetime",
        "__module__": "datetime"
    },
    "updated_at": {
        "datetime": "2023-01-02 12:13:25.000000",
        "tzinfo": null,
        "__class__": "datetime",
        "__module__": "datetime"
    },
    "my_number": {
        "value": 5,
        "__class__": "Number",
        "__module__": "tests.tools.serde.conftest"
    },
    "__class__": "PydanticWithTrickyTypes",
    "__module__": "tests.tools.serde.conftest"
}"""


obj_class_tricky_types = ClassWithTrickyTypes(
    data={
        "created_at": datetime(2023, 1, 1, 12, 0, 0),
        "updated_at": datetime(2023, 1, 2, 12, 13, 25),
        "my_number": Number(value=42),
    }
)


MyDictType = Dict[str, Any]


class MyRootModel(RootModel[MyDictType]):
    def check(self):
        if not self.root:
            log.debug("self.root is empty")
        log.debug(f"self.root.items(): {self.root.items()}")
        log.debug(f"self.root: {self.root}")


my_root_model = MyRootModel(root={"a": 1, "b": 2})


class SerDeTestCases:
    PYDANTIC_EXAMPLES: ClassVar[List[BaseModel]] = [
        obj_pydantic_tricky_types,
        obj_pydantic_tricky_sub_classes,
        my_root_model,
    ]
    PYDANTIC_FULL_CHECKS: ClassVar[List[Tuple[BaseModel, Dict[str, Any], Dict[str, Any], str]]] = [
        (
            obj_pydantic_tricky_types,
            obj_pydantic_tricky_types_dict,
            obj_pydantic_tricky_types_dict_typed,
            obj_pydantic_tricky_types_json_str4,
        )
    ]
    ARBITRARY_TYPES: ClassVar[List[Any]] = [
        my_root_model,
        obj_class_tricky_types,
    ]
    LISTS: ClassVar[List[List[Any]]] = [
        [
            my_root_model,
            obj_pydantic_tricky_types,
            obj_pydantic_tricky_sub_classes,
            obj_class_tricky_types,
        ],
    ]
