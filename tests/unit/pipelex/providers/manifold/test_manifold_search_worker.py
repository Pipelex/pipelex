"""The search worker's wire body and its usage translation.

The translation is the same silent failure the extract worker has, in the other unit: the route
reports `usage.searches` and the runtime prices per million, so an untranslated response leaves
`nb_tokens_by_category` empty and `linkup-standard` at `costs = { input = 0.005 }` prices nothing at
all, with no exception and no warning.

The body carries **no `depth`**: the model id is where that lives — `linkup/standard` versus
`linkup/deep` — and a second source for a decision the gateway takes from one place is a source of
disagreement rather than of flexibility.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from pydantic import BaseModel

from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.providers.manifold.manifold_exceptions import ManifoldSearchEmptyResultError, ManifoldSearchResponseError
from pipelex.providers.manifold.manifold_extract_worker import MANIFOLD_UNIT_TOKENS
from pipelex.providers.manifold.manifold_search_worker import ManifoldSearchWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_SOURCED_ANSWER = {
    "answer": "A manifold is a topological space that locally resembles Euclidean space.",
    "sources": [{"name": "Manifold", "url": "https://example.com/manifold", "snippet": "locally Euclidean"}],
    "usage": {"searches": 1},
}


class _Capital(BaseModel):
    city: str


def _make_worker(mocker: MockerFixture, *, response_body: dict[str, Any] | None = None) -> ManifoldSearchWorker:
    worker = object.__new__(ManifoldSearchWorker)
    model = mocker.MagicMock()
    model.model_id = "linkup/standard"
    model.name = "linkup-sourced-answer"
    model.desc = "test-manifold-search"
    worker.inference_model = model
    client = mocker.MagicMock()
    client.post_json = mocker.AsyncMock(return_value=response_body if response_body is not None else _SOURCED_ANSWER)
    worker.client = client
    return worker


def _post_json(worker: ManifoldSearchWorker) -> Any:
    """The stand-in for the native client, as `Any` so its mock attributes typecheck."""
    return worker.client.post_json


def _make_search_job(mocker: MockerFixture) -> Any:
    job = mocker.MagicMock()
    job.query = "what is a manifold"
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
class TestManifoldSearchRequestBody:
    async def test_the_body_names_the_model_and_carries_no_depth(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)

        await worker._search_sourced_answer(_make_search_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        call = _post_json(worker).call_args.kwargs
        assert call["route"] == "/pipelex/search"
        assert call["body"]["model"] == "linkup/standard"
        assert call["body"]["query"] == "what is a manifold"
        assert "depth" not in call["body"]

    async def test_unset_optional_parameters_are_omitted_rather_than_sent_as_null(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)

        await worker._search_sourced_answer(_make_search_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        body = _post_json(worker).call_args.kwargs["body"]
        for absent in ("include_domains", "exclude_domains", "from_date", "to_date", "output_schema"):
            assert absent not in body

    async def test_a_structured_search_sends_the_caller_s_schema(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, response_body={"data": {"city": "Paris"}, "sources": [], "usage": {"searches": 1}})

        result = await worker._search_structured(_make_search_job(mocker), schema=_Capital)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == {"city": "Paris"}
        body = _post_json(worker).call_args.kwargs["body"]
        assert body["output_schema"] == _Capital.model_json_schema()


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldSearchResponse:
    async def test_a_sourced_answer_becomes_the_runtime_s_own_content(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)

        result = await worker._search_sourced_answer(_make_search_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert isinstance(result, SearchResultContent)
        assert result.answer.startswith("A manifold is")
        assert [source.url for source in result.sources] == ["https://example.com/manifold"]

    async def test_a_response_with_no_answer_is_refused_rather_than_returned_empty(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, response_body={"sources": [], "usage": {"searches": 1}})

        with pytest.raises(ManifoldSearchResponseError):
            await worker._search_sourced_answer(_make_search_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_a_structured_search_that_found_nothing_says_so(self, mocker: MockerFixture) -> None:
        """The query's fault, not the model's — which is why it carries CHANGE_INPUT."""
        worker = _make_worker(mocker, response_body={"data": None, "sources": [], "usage": {"searches": 1}})

        with pytest.raises(ManifoldSearchEmptyResultError):
            await worker._search_structured(_make_search_job(mocker), schema=_Capital)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_the_usage_key_does_not_stop_the_envelope_being_recognised(self, mocker: MockerFixture) -> None:
        """The route puts `usage` beside the envelope, and it must not reach the unwrapper.

        `extract_structured_search_payload` recognises the envelope by its key set being *exactly*
        `data` and `sources`. Hand it a third key and it returns the whole body as the payload —
        which validates against an output class whose fields have defaults and yields an
        all-defaults object, with no exception and no warning. The failure has no symptom at all
        beyond a wrong answer, so it is pinned rather than left to the shape of the fixture.
        """
        worker = _make_worker(mocker, response_body={"data": {"city": "Paris"}, "sources": [], "usage": {"searches": 1}})

        result = await worker._search_structured(_make_search_job(mocker), schema=_Capital)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert result == {"city": "Paris"}
        assert "usage" not in result
        assert "sources" not in result


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldSearchUsageTranslation:
    async def test_searches_become_megatokens_in_both_categories(self, mocker: MockerFixture) -> None:
        """The same cost figure the Portkey path reports, which is what makes the two comparable."""
        worker = _make_worker(mocker, response_body={**_SOURCED_ANSWER, "usage": {"searches": 2}})
        job = _make_search_job(mocker)
        usage = mocker.MagicMock()
        job.job_report.search_tokens_usage = usage

        await worker._search_sourced_answer(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert usage.nb_tokens_by_category == {
            TokenCategory.INPUT: 2 * MANIFOLD_UNIT_TOKENS,
            TokenCategory.OUTPUT: 2 * MANIFOLD_UNIT_TOKENS,
        }

    @pytest.mark.parametrize(
        "usage_block",
        [None, {}, {"searches": "one"}],
        ids=["null-usage", "empty-usage", "non-numeric-searches"],
    )
    async def test_a_usage_block_the_route_did_not_send_leaves_the_categories_untouched(
        self,
        mocker: MockerFixture,
        usage_block: dict[str, Any] | None,
    ) -> None:
        worker = _make_worker(mocker, response_body={**_SOURCED_ANSWER, "usage": usage_block})
        job = _make_search_job(mocker)
        usage = mocker.MagicMock()
        empty_categories: NbTokensByCategoryDict = {}
        usage.nb_tokens_by_category = empty_categories
        job.job_report.search_tokens_usage = usage

        await worker._search_sourced_answer(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert usage.nb_tokens_by_category == {}
