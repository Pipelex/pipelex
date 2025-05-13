# SPDX-FileCopyrightText: © 2025 Evotis S.A.S.
# SPDX-License-Identifier: Elastic-2.0
# "Pipelex" is a trademark of Evotis S.A.S.

import json
from typing import Any, Dict

import pytest
from pydantic import BaseModel

from pipelex import pretty_print

from .conftest import SerDeTestCases


class TestSerDePydanticByDict:
    @pytest.mark.parametrize("test_obj, test_obj_dict, test_obj_dict_typed, test_obj_json_str4", SerDeTestCases.PYDANTIC_FULL_CHECKS)
    def test_dump_dict_validate(
        self,
        test_obj: BaseModel,
        test_obj_dict: Dict[str, Any],
        test_obj_dict_typed: Dict[str, Any],
        test_obj_json_str4: str,
    ):
        # Serialize the model to a dictionary
        deserialized_dict = test_obj.model_dump()
        pretty_print(deserialized_dict, title="Serialized")
        assert deserialized_dict == test_obj_dict_typed

        # Validate the dictionary back to a model
        the_class = type(test_obj)
        deserialized = the_class.model_validate(deserialized_dict)
        pretty_print(deserialized, title="Deserialized")

        assert test_obj == deserialized

    @pytest.mark.parametrize("test_obj, test_obj_dict, test_obj_dict_typed, test_obj_json_str4", SerDeTestCases.PYDANTIC_FULL_CHECKS)
    def test_serde_dump_json_load_validate(
        self,
        test_obj: BaseModel,
        test_obj_dict: Dict[str, Any],
        test_obj_dict_typed: Dict[str, Any],
        test_obj_json_str4: str,
    ):
        # Serialize the model to a json string
        serialized_str = test_obj.model_dump_json()
        pretty_print(serialized_str, title="Serialized JSON")

        # Deserialize the json string back to a dictionary
        deserialized_dict = json.loads(serialized_str)
        assert deserialized_dict == test_obj_dict
        pretty_print(deserialized_dict, title="Deserialized to dict")
        assert deserialized_dict["created_at"] == "2023-01-01T12:00:00"
        assert deserialized_dict["updated_at"] == "2023-01-02T12:13:25"

        # Validate the dictionary back to a model
        the_class = type(test_obj)
        validated_model = the_class.model_validate(deserialized_dict)
        pretty_print(validated_model, title="Validated model")

        assert test_obj == validated_model
