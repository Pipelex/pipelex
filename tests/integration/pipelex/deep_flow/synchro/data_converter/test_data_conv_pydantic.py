from typing import Any

import pytest
from pydantic import RootModel

from pipelex import pretty_print
from pipelex.deep_flow.temporal_data_converter import BaseModelPayloadConverter


class MyRootModel(RootModel[dict[str, Any]]):
    pass


@pytest.mark.temporal
class TestDataConverterForRootModel:
    def test_data_converter_for_root_model_with_dict(
        self,
        payload_converter: BaseModelPayloadConverter,
    ):
        my_root_model_1 = MyRootModel(root={"a": 1, "b": 2})
        pretty_print(my_root_model_1, title="my_root_model_1")
        payload = payload_converter.to_payload(my_root_model_1)
        pretty_print(payload, title="payload")
        assert payload
        restored: MyRootModel = payload_converter.from_payload(payload, type_hint=MyRootModel)
        pretty_print(restored, title="restored MyRootModel")
        assert restored
        assert my_root_model_1 == restored
