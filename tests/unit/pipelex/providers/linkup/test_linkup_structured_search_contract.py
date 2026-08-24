"""What a structured search must put on the wire, and what it must hand back.

The leaf validates the returned dict against the caller's output structure class, so the worker owes it
exactly that payload — and owes it *unvalidated*, because the leaf is where the run mode and the
dry-run fidelity contract live. Two things make that true, and both are invisible from the outside:

- the schema crosses as a JSON string, not as the class. Byte-for-byte the same request, but handing the
  SDK the class also makes it instantiate that class from the response, which would run the caller's
  validators inside the SDK and again at the leaf;
- sources are not requested, because a structured result has nowhere to put them and asking for them
  wraps the payload in an envelope no output class can accept.

No provider is called (the SDK client is mocked), so this needs no inference marker.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel, Field, field_validator

from pipelex.providers.linkup.linkup_exceptions import LinkupSearchEmptyResultError, LinkupSearchResponseError
from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


class TopicSummary(BaseModel):
    """An output structure carrying invariants a JSON-schema rebuild would drop."""

    title: str = Field(json_schema_extra={"mock_format": "name"})
    summary: str

    @field_validator("title")
    @classmethod
    def _require_prefix(cls, value: str) -> str:
        return f"INV-{value}"


class AllDefaults(BaseModel):
    """An output structure with no required field — the shape that makes a wrong payload validate silently."""

    title: str = "untitled"
    summary: str = ""


def _make_worker(mocker: MockerFixture, *, sdk_result: Any) -> LinkupSearchWorker:
    worker = object.__new__(LinkupSearchWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-linkup-search"
    mock_model.model_id = "linkup/standard"
    mock_model.name = "linkup-standard"
    worker.inference_model = mock_model
    mock_client = mocker.MagicMock()
    mock_client.async_search = mocker.AsyncMock(return_value=sdk_result)
    setattr(worker, "_linkup_client", mock_client)  # ruff: ignore[set-attr-with-constant]
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
class TestLinkupStructuredSearchContract:
    async def test_the_callers_own_schema_crosses_as_json_without_the_class(self, mocker: MockerFixture) -> None:
        """The request carries the caller's real schema, and the SDK gets no class to instantiate."""
        worker = _make_worker(mocker, sdk_result={"title": "pipelex", "summary": "a language"})
        client: Any = getattr(worker, "_linkup_client")  # ruff: ignore[get-attr-with-constant]

        await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        sent_schema = client.async_search.await_args.kwargs["structured_output_schema"]
        assert isinstance(sent_schema, str), "a class would make the SDK validate the response itself"
        assert json.loads(sent_schema) == TopicSummary.model_json_schema()
        # The hint a schema rebuild would have dropped is in the request, which is the point of
        # threading the caller's class this far down.
        assert json.loads(sent_schema)["properties"]["title"]["mock_format"] == "name"

    async def test_sources_are_not_requested(self, mocker: MockerFixture) -> None:
        """Asking for sources wraps the payload in an envelope the output structure class cannot accept."""
        worker = _make_worker(mocker, sdk_result={"title": "pipelex", "summary": "a language"})
        client: Any = getattr(worker, "_linkup_client")  # ruff: ignore[get-attr-with-constant]

        await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert client.async_search.await_args.kwargs["include_sources"] is False

    async def test_the_payload_comes_back_raw_and_validates_into_the_output_class(self, mocker: MockerFixture) -> None:
        """The dict is the structured payload itself, un-normalized: the leaf's validation is the first one."""
        worker = _make_worker(mocker, sdk_result={"title": "pipelex", "summary": "a language"})

        result = await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == {"title": "pipelex", "summary": "a language"}
        # The caller's transforming validator has not run yet — it runs once, when the leaf validates.
        validated = TopicSummary.model_validate(result)
        assert validated.title == "INV-pipelex"

    async def test_an_unrequested_envelope_is_unwrapped_rather_than_silently_validated(self, mocker: MockerFixture) -> None:
        """Not requesting sources is not the same as not receiving them, and the difference is silent.

        Asking `include_sources=False` is a request, not a guarantee — the SDK's own source hedges on it
        ("we assume that include_sources will default to False, since the API output can be arbitrary").
        A provider that ignores the flag hands back the envelope, and an output structure whose fields all
        carry defaults validates that envelope *successfully* into an all-defaults object, because
        pydantic's default `extra="ignore"` drops both keys. That is wrong answers with no error, so the
        shape is recognised rather than assumed.
        """
        payload = {"title": "pipelex", "summary": "a language"}
        envelope = {"data": payload, "sources": [{"name": "src", "url": "https://example.com", "snippet": "…"}]}
        worker = _make_worker(mocker, sdk_result=envelope)

        result = await worker._search_structured(search_job=_make_search_job(mocker), schema=AllDefaults)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == payload
        # What the guard prevents: validating the envelope instead would have succeeded and thrown the
        # provider's real answer away.
        assert AllDefaults.model_validate(envelope).title == "untitled"

    async def test_an_envelope_carrying_no_payload_raises_an_empty_result_error(self, mocker: MockerFixture) -> None:
        """A search that found nothing is not a malformed response — it must not advise changing model."""
        worker = _make_worker(mocker, sdk_result={"data": None, "sources": []})

        with pytest.raises(LinkupSearchEmptyResultError, match="empty structured result"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_a_non_object_payload_raises_a_classified_search_error(self, mocker: MockerFixture) -> None:
        """The SDK returns the provider's JSON verbatim, so a non-object payload must surface here as a classified error, not at the leaf."""
        worker = _make_worker(mocker, sdk_result=["not", "an", "object"])

        with pytest.raises(LinkupSearchResponseError, match="list"):
            await worker._search_structured(search_job=_make_search_job(mocker), schema=TopicSummary)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]
