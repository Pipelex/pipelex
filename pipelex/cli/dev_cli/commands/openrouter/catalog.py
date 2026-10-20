"""Read the public catalog without depending on hosted-plane configuration."""

import os
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

CATALOG_URL = "https://openrouter.ai/api/v1/models"


class OpenRouterArchitecture(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    input_modalities: list[str] = Field(default_factory=list)
    output_modalities: list[str] = Field(default_factory=list)


class OpenRouterModel(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    id: str = Field(min_length=1)
    name: str = ""
    created: int | None = None
    context_length: int | None = None
    architecture: OpenRouterArchitecture | None = None
    pricing: dict[str, Any] | None = None
    top_provider: dict[str, Any] | None = None
    supported_parameters: list[str] = Field(default_factory=list)


class CatalogPage(BaseModel):
    model_config = ConfigDict(strict=True)

    data: list[OpenRouterModel]
    links: dict[str, str | None] | None = None


def fetch_models(*, category: str | None = None) -> list[OpenRouterModel]:
    """Fetch all modalities, retaining the first occurrence of each model ID."""
    headers = {"Accept": "application/json"}
    if api_key := os.getenv("OPENROUTER_API_KEY"):
        headers["Authorization"] = f"Bearer {api_key}"
    initial_params = {"output_modalities": "all"}
    if category:
        initial_params["category"] = category
    params: dict[str, str] | None = initial_params
    models: dict[str, OpenRouterModel] = {}
    seen_pages: set[str] = set()
    next_url: str | None = CATALOG_URL
    with httpx.Client(timeout=30.0, headers=headers) as client:
        while next_url:
            parsed = urlsplit(next_url)
            if (parsed.scheme, parsed.netloc, parsed.path) != ("https", "openrouter.ai", "/api/v1/models") or next_url in seen_pages:
                msg = "OpenRouter returned an invalid catalog pagination link"
                raise ValueError(msg)
            seen_pages.add(next_url)
            response = client.get(next_url, params=params)
            response.raise_for_status()
            page = CatalogPage.model_validate(response.json())
            for model in page.data:
                models.setdefault(model.id, model)
            next_link = (page.links or {}).get("next")
            next_url = urljoin(CATALOG_URL, next_link) if next_link else None
            params = None
    return list(models.values())
