"""Catalog transport, command output and validated backend exports."""

from typing import Any

import pytest
import tomli

from pipelex.cli.dev_cli.commands.openrouter.catalog import OpenRouterModel
from pipelex.cli.dev_cli.commands.openrouter.export import models_to_toml
from pipelex.cogt.model_backends.model_spec_document import describe_model_spec_document_rejection


class TestOpenRouterExport:
    def test_validated_drafts(self, catalog_models: list[dict[str, Any]]) -> None:
        models = [OpenRouterModel.model_validate(model) for model in catalog_models]
        document = tomli.loads(models_to_toml(models=models))
        assert describe_model_spec_document_rejection(document=document) is None
        text = document["acme/text.v1:free"]
        assert text["max_tokens"] == 4096
        assert text["enabled"] is False
        assert text["inputs"] == ["text", "images", "pdf"]
        assert text["outputs"] == ["text"]
        assert "structure_method" not in text
        assert text["costs"] == {"input": 3.0, "output": 15.0}
        image = document["acme/image"]
        assert image["sdk"] == "openrouter_img_gen"
        assert "costs" not in image
        assert "max_tokens" not in image

    def test_explicit_structured_and_quoted_key(self, catalog_models: list[dict[str, Any]]) -> None:
        model = OpenRouterModel.model_validate(catalog_models[0])
        model.id = 'vendor/quoted"name'
        model.supported_parameters = ["structured_outputs"]
        document = tomli.loads(models_to_toml(models=[model]))
        assert document[model.id]["outputs"] == ["text", "structured"]
        assert describe_model_spec_document_rejection(document=document) is None

    @pytest.mark.parametrize("price", [None, "-1", "NaN", "Infinity", "not a price"])
    def test_unknown_prices(self, catalog_models: list[dict[str, Any]], price: str | None) -> None:
        model = OpenRouterModel.model_validate(catalog_models[0])
        model.pricing = {"prompt": price}
        document = tomli.loads(models_to_toml(models=[model]))
        assert "costs" not in document[model.id]
