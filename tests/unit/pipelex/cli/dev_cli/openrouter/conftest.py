from typing import Any

import pytest
from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands.openrouter.catalog import OpenRouterModel


@pytest.fixture
def catalog_models() -> list[dict[str, Any]]:
    return [
        {
            "id": "acme/text.v1:free",
            "name": "Text | Model",
            "created": 100,
            "context_length": 32000,
            "architecture": {"input_modalities": ["text", "image", "file"], "output_modalities": ["text"]},
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
            "top_provider": {"max_completion_tokens": 4096},
            "supported_parameters": ["tools"],
        },
        {
            "id": "acme/image",
            "name": "Image Model",
            "created": 200,
            "context_length": 8000,
            "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["image"]},
            "pricing": {"prompt": None, "completion": "-1"},
            "supported_parameters": [],
        },
    ]


@pytest.fixture
def mocked_catalog(mocker: MockerFixture, catalog_models: list[dict[str, Any]]) -> None:
    mocker.patch(
        "pipelex.cli.dev_cli.commands.openrouter.openrouter_cmd.fetch_models",
        return_value=[OpenRouterModel.model_validate(model) for model in catalog_models],
    )
