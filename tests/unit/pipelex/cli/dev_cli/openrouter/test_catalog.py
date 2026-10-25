"""Catalog transport, command output and validated backend exports."""

from typing import Any

import httpx
import pytest
from pytest_mock import MockerFixture

from pipelex.cli.dev_cli.commands.openrouter.catalog import fetch_models


class TestOpenRouterCatalog:
    def test_all_modalities_auth_category_pagination(self, mocker: MockerFixture, catalog_models: list[dict[str, Any]]) -> None:
        mocker.patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"})
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if len(requests) == 1:
                return httpx.Response(200, json={"data": catalog_models[:1], "links": {"next": "/api/v1/models?offset=1"}})
            return httpx.Response(200, json={"data": catalog_models, "links": {"next": None}})

        client = httpx.Client(transport=httpx.MockTransport(respond))
        constructor = mocker.patch("pipelex.cli.dev_cli.commands.openrouter.catalog.httpx.Client", return_value=client)
        models = fetch_models(category="programming")
        assert [model.id for model in models] == [model["id"] for model in catalog_models]
        assert requests[0].url.params["output_modalities"] == "all"
        assert requests[0].url.params["category"] == "programming"
        assert requests[1].url.params["offset"] == "1"
        assert constructor.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"

    def test_anonymous_lookup(self, mocker: MockerFixture) -> None:
        mocker.patch.dict("os.environ", {}, clear=True)
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": []})))
        constructor = mocker.patch("pipelex.cli.dev_cli.commands.openrouter.catalog.httpx.Client", return_value=client)
        assert fetch_models() == []
        assert "Authorization" not in constructor.call_args.kwargs["headers"]

    @pytest.mark.parametrize("next_link", ["https://attacker.example/models", "https://openrouter.ai/api/v1/models"])
    def test_rejects_unsafe_or_repeated_pages(self, mocker: MockerFixture, next_link: str) -> None:
        client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"data": [], "links": {"next": next_link}})))
        mocker.patch("pipelex.cli.dev_cli.commands.openrouter.catalog.httpx.Client", return_value=client)
        with pytest.raises(ValueError, match="pagination"):
            fetch_models()
