# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

from typing import Any, Dict

from pydantic import RootModel

from pipelex import log

MyDictType = Dict[str, Any]


class MyRootModel(RootModel[MyDictType]):
    def check(self):
        if not self.root:
            log.debug("self.root is empty")
        log.debug(f"self.root.items(): {self.root.items()}")
        log.debug(f"self.root: {self.root}")


class TestPydantic:
    def test_root_model(self):
        my_root_model_1 = MyRootModel(root={"a": 1, "b": 2})
        log.debug(my_root_model_1)
        log.debug(f"my_root_model_1.root: {my_root_model_1.root}")

        my_root_model_2 = MyRootModel(root={})
        log.debug(my_root_model_2)
        log.debug(f"my_root_model_2.root: {my_root_model_2.root}")
        if not my_root_model_2.root:
            log.debug("my_root_model_2.root is empty")

        my_root_model_2.check()

    def test_validate_root_model(self):
        my_root_model_3_dict = {"root": {"a": 1, "b": 2}}
        my_root_model_3 = MyRootModel.model_validate(my_root_model_3_dict)
        log.debug(my_root_model_3)
