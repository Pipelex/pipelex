from typing import Any

import pytest
from kajson import kajson
from pydantic import BaseModel

from pipelex import pretty_print
from pipelex.cogt.llm.llm_prompt_template import LLMPromptTemplate
from tests.integration.pipelex.cogt.test_data import SerDeTestLLMCases


class TestSerDeLLMClasses:
    @pytest.mark.parametrize("test_obj", SerDeTestLLMCases.PYDANTIC_EXAMPLES + SerDeTestLLMCases.PYDANTIC_EXAMPLES_USING_SUBCLASS)
    def test_serde_by_str(self, test_obj: Any):
        # Serialize the model to a json string
        serialized_str: str = kajson.dumps(test_obj, indent=4)  # pyright: ignore[reportUnknownMemberType]
        pretty_print(serialized_str, title="Serialized JSON")
        deserialized = kajson.loads(serialized_str)  # pyright: ignore[reportUnknownMemberType]
        pretty_print(deserialized, title=f"Deserialized by kajson as {type(deserialized).__name__}")

        # Assertions to ensure the process worked correctly
        assert test_obj == deserialized

    @pytest.mark.parametrize("test_obj", SerDeTestLLMCases.PYDANTIC_EXAMPLES)
    def test_serde_by_dump(
        self,
        test_obj: BaseModel,
    ):
        # Note: serde_by_dump, based on pydantic model_dump, doesn't handle subclasses

        # Serialize the model to a dictionary
        deserialized_dict = test_obj.model_dump(serialize_as_any=True)
        pretty_print(deserialized_dict, title="Serialized")

        # Validate the dictionary back to a model
        the_class = type(test_obj)
        deserialized = the_class.model_validate(deserialized_dict)
        pretty_print(deserialized, title="Deserialized")

        assert test_obj == deserialized

    @pytest.mark.parametrize("test_dict", SerDeTestLLMCases.PYDANTIC_EXAMPLES_DICT)
    def test_serde_model_validate_from_dict(
        self,
        test_dict: dict[str, Any],
    ):
        pretty_print(test_dict, title="Original dict")
        # Deserialize the dictionary to a LLMPromptTemplate model
        the_obj = LLMPromptTemplate.model_validate(test_dict)
        pretty_print(the_obj, title="Deserialized from dict")

        # Serialize the model to a dictionary
        deserialized_dict = the_obj.model_dump(serialize_as_any=True)
        pretty_print(deserialized_dict, title="Serialized")

        # Validate the dictionary back to a model
        the_class = type(the_obj)
        deserialized = the_class.model_validate(deserialized_dict)
        pretty_print(deserialized, title="Deserialized")

        assert the_obj == deserialized

    @pytest.mark.parametrize("test_dict", SerDeTestLLMCases.PYDANTIC_EXAMPLES_DICT)
    def test_serde_instantiate_from_kwargs(
        self,
        test_dict: dict[str, Any],
    ):
        pretty_print(test_dict, title="Original dict")
        # Deserialize the dictionary to a LLMPromptTemplate model
        the_obj = LLMPromptTemplate(**test_dict)
        pretty_print(the_obj, title="Deserialized from dict")

        # Serialize the model to a dictionary
        deserialized_dict = the_obj.model_dump(serialize_as_any=True)
        pretty_print(deserialized_dict, title="Serialized")

        # Validate the dictionary back to a model
        the_class = type(the_obj)
        deserialized = the_class.model_validate(deserialized_dict)
        pretty_print(deserialized, title="Deserialized")

        assert the_obj == deserialized
