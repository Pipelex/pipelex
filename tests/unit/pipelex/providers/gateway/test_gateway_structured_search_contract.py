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

from pipelex.providers.gateway.gateway_exceptions import GatewaySearchEmptyResultError, GatewaySearchResponseError
from pipelex.providers.gateway.gateway_search_worker import GatewaySearchWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TopicSummary(BaseModel):
    title: str
    summary: str


class DataAndSources(BaseModel):
    """An output structure that legitimately spells its own fields the way the relay envelope does."""

    data: dict[str, str]
    sources: list[str]


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

    async def test_a_bare_payload_passes_through_unwrapped(self, mocker: MockerFixture) -> None:
        """The relay dropping sources must not break this worker — the envelope is recognised, not demanded.

        Demanding it would make "relay stops asking Linkup for sources" a coordinated two-sided deploy:
        every gateway structured search would fail until both repos shipped together.
        """
        payload = {"title": "pipelex", "summary": "a language"}
        worker = _make_worker(mocker, content=json.dumps(payload))

        result = await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result == payload

    async def test_an_output_class_that_declares_data_and_sources_is_not_unwrapped(self, mocker: MockerFixture) -> None:
        """The one shape a positional `.get("data")` unwrap would silently corrupt."""
        payload = {"data": {"nested": "value"}, "sources": ["a"]}
        worker = _make_worker(mocker, content=json.dumps(payload))

        result = await worker._search_structured(search_job=_make_search_job(mocker), schema=DataAndSources)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

        assert result == payload, "the caller's own {data, sources} output is its payload, not an envelope around one"

    async def test_an_envelope_carrying_no_payload_raises_an_empty_result_error(self, mocker: MockerFixture) -> None:
        """A search that found nothing is not a malformed response — it must not advise changing model."""
        worker = _make_worker(mocker, content=json.dumps({"data": None, "sources": []}))

        with pytest.raises(GatewaySearchEmptyResultError, match="empty structured result"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    async def test_a_non_object_response_raises_a_classified_search_error(self, mocker: MockerFixture) -> None:
        """A response that is not a JSON object at all is malformed, and says so."""
        worker = _make_worker(mocker, content=json.dumps(["not", "an", "object"]))

        with pytest.raises(GatewaySearchResponseError, match="non-object payload"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    async def test_a_non_json_body_raises_a_classified_search_error(self, mocker: MockerFixture) -> None:
        """The likeliest way the relay contract breaks must not escape as a bare JSONDecodeError."""
        worker = _make_worker(mocker, content="<html>502 Bad Gateway</html>")

        with pytest.raises(GatewaySearchResponseError, match="not valid JSON"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]
