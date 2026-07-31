"""The gateway's structured search must hand the leaf the bare payload, not the relay's envelope.

The relay asks Linkup for sources alongside the structured payload, so its wire shape is a
``{data, sources}`` envelope — while the leaf validates the result against the caller's output
structure class, which has nowhere to put sources. The worker owes the leaf the unwrapped payload,
and owes a classified search error (not an opaque downstream ``ValidationError``) when the envelope
shape is not there.

No provider is called (the relay call is mocked), so this needs no inference marker.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

from pipelex.providers.gateway.gateway_exceptions import GatewaySearchResponseError
from pipelex.providers.gateway.gateway_search_worker import GatewaySearchWorker


class TopicSummary(BaseModel):
    title: str
    summary: str


def _make_worker(mocker: MockerFixture, *, content: str) -> GatewaySearchWorker:
    worker = object.__new__(GatewaySearchWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-gateway-search"
    mock_model.model_id = "linkup/standard"
    mock_model.name = "linkup-standard"
    mock_model.extra_headers = None
    worker.inference_model = mock_model
    mocker.patch.object(GatewaySearchWorker, "_call_relay", mocker.AsyncMock(return_value=mocker.MagicMock()))
    mocker.patch.object(GatewaySearchWorker, "_extract_usage", return_value=None)
    mocker.patch.object(GatewaySearchWorker, "_extract_content", return_value=content)
    return worker


def _make_search_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.query = "test search query"
    job.job_params.search_setting.include_images = False
    job.job_params.search_setting.include_inline_citations = False
    job.job_params.search_setting.max_results = 10
    job.job_params.include_domains = None
    job.job_params.exclude_domains = None
    job.job_params.from_date = None
    job.job_params.to_date = None
    job.job_report.search_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestGatewayStructuredSearchContract:
    async def test_the_relay_envelope_is_unwrapped_to_the_bare_payload(self, mocker: MockerFixture) -> None:
        """The `{data, sources}` envelope arrives from the relay; the leaf gets the payload alone."""
        payload = {"title": "pipelex", "summary": "a language"}
        content = json.dumps({"data": payload, "sources": [{"name": "src", "url": "https://example.com", "snippet": "…"}]})
        worker = _make_worker(mocker, content=content)

        result = await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result == payload
        # The payload validates against the caller's output structure class — the envelope never could.
        validated = TopicSummary.model_validate(result)
        assert validated.title == "pipelex"

    async def test_a_missing_data_key_raises_a_classified_search_error(self, mocker: MockerFixture) -> None:
        """A relay response without the envelope fails here as a classified error, not at the leaf."""
        worker = _make_worker(mocker, content=json.dumps({"title": "pipelex", "summary": "a language"}))

        with pytest.raises(GatewaySearchResponseError, match="envelope"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    async def test_a_non_object_response_raises_a_classified_search_error(self, mocker: MockerFixture) -> None:
        """A response that is not even a JSON object fails the same way."""
        worker = _make_worker(mocker, content=json.dumps(["not", "an", "object"]))

        with pytest.raises(GatewaySearchResponseError, match="envelope"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
