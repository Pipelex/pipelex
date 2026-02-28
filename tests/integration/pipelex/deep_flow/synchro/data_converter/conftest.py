import pytest

from pipelex.deep_flow.temporal_data_converter import BaseModelPayloadConverter


@pytest.fixture
def payload_converter() -> BaseModelPayloadConverter:
    return BaseModelPayloadConverter()


class CraftingTestCases:
    USER_TEXT_FOR_BASE = """
    Write a detailed description of a woman's clothing in the style of a 19th-century novel.
    Keep it short: 3 sentences max
    """

    USER_TEXT_FOR_SINGLE_PERSON = "name: John, age: 30, job: bank teller"
