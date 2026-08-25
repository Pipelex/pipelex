"""The extract worker's three invisible failure modes.

**The usage translation.** The native route reports honest counts (`usage.pages`) and the runtime's
cost model is per million tokens. Untranslated, `nb_tokens_by_category` simply stays empty — no
exception, no warning — and the job reports a cost of zero. There is nothing to notice, which is why
it is pinned here against the figure the Portkey path reports for the same work.

**The withdrawn parameters.** `ExtractJobParams` carries fields the frozen contract deliberately
does not, and the gateway refuses them at *any* value including their own defaults. A worker that
reached for `model_dump()` would send `should_caption_images=false` and be refused — at request
time, in production, with a message about a parameter nobody meant to send.

**The input form.** Which one a model takes follows from what the catalog says, not from a list of
model names kept in step by hand: a web-page extractor is handed the page's own URL, everything else
is handed the bytes inline. The gateway holds no credentials for our storage, so a local path or a
`pipelex-storage://` URI must become bytes on this side.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from pipelex.cogt.extract.exceptions import ExtractInputError
from pipelex.cogt.usage.token_category import NbTokensByCategoryDict, TokenCategory
from pipelex.providers.manifold.manifold_extract_worker import MANIFOLD_UNIT_TOKENS, ManifoldExtractWorker

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_PDF_BYTES_URL = "data:application/pdf;base64,JVBERi0xLjQK"


def _make_worker(
    mocker: MockerFixture,
    *,
    is_web_page_supported: bool = False,
    response_body: dict[str, Any] | None = None,
) -> ManifoldExtractWorker:
    worker = object.__new__(ManifoldExtractWorker)
    model = mocker.MagicMock()
    model.model_id = "adi/prebuilt-layout"
    model.name = "azure-document-intelligence"
    model.desc = "test-manifold-extract"
    model.is_web_page_supported_for_extract = is_web_page_supported
    worker.inference_model = model
    client = mocker.MagicMock()
    client.post_json = mocker.AsyncMock(return_value=response_body if response_body is not None else {"pages": {}, "usage": {"pages": 3}})
    worker.client = client
    return worker


def _post_json(worker: ManifoldExtractWorker) -> Any:
    """The stand-in for the native client, as `Any` so its mock attributes typecheck."""
    return worker.client.post_json


def _make_extract_job(mocker: MockerFixture, *, document_uri: str | None = None, image_uri: str | None = None) -> Any:
    job = mocker.MagicMock()
    job.extract_input.document_uri = document_uri
    job.extract_input.image_uri = image_uri
    job.job_params.max_nb_images = None
    job.job_params.render_js = None
    job.job_params.include_raw_html = None
    job.job_report.extract_tokens_usage = None
    return job


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldExtractRequestBody:
    async def test_the_withdrawn_parameters_are_absent_rather_than_sent_at_their_defaults(self, mocker: MockerFixture) -> None:
        """`should_caption_images=false` is refused by the gateway exactly as loudly as `true` is."""
        worker = _make_worker(mocker)
        mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=_PDF_BYTES_URL,
        )
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")

        await worker._extract_pages(_make_extract_job(mocker, document_uri="/local/report.pdf"))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        body = _post_json(worker).call_args.kwargs["body"]
        rendered = str(body)
        for withdrawn in ("image_min_size", "should_caption_images", "should_include_page_views", "page_views_dpi"):
            assert withdrawn not in rendered, f"the withdrawn parameter '{withdrawn}' reached the wire"

    async def test_an_unset_optional_parameter_is_omitted_rather_than_sent_as_null(self, mocker: MockerFixture) -> None:
        """The gateway refuses `render_js` on a provider that cannot honour it, null included."""
        worker = _make_worker(mocker)
        mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=_PDF_BYTES_URL,
        )
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")

        await worker._extract_pages(_make_extract_job(mocker, document_uri="/local/report.pdf"))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        body = _post_json(worker).call_args.kwargs["body"]
        assert body["params"] == {}
        assert body["input"] == {"document_uri": _PDF_BYTES_URL}
        assert body["model"] == "adi/prebuilt-layout"

    async def test_a_web_page_model_is_handed_the_url_itself(self, mocker: MockerFixture) -> None:
        """The gateway fetches `https:` on this path; turning the page into bytes here would fetch it twice."""
        worker = _make_worker(mocker, is_web_page_supported=True)
        fetch = mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
        )

        await worker._extract_pages(_make_extract_job(mocker, document_uri="https://example.com/article"))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        body = _post_json(worker).call_args.kwargs["body"]
        assert body["input"] == {"document_uri": "https://example.com/article"}
        fetch.assert_not_awaited()

    async def test_a_non_web_page_model_is_handed_the_bytes_inline(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        fetch = mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=_PDF_BYTES_URL,
        )
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")

        await worker._extract_pages(_make_extract_job(mocker, document_uri="pipelex-storage://bucket/report.pdf"))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        body = _post_json(worker).call_args.kwargs["body"]
        assert body["input"] == {"document_uri": _PDF_BYTES_URL}
        fetch.assert_awaited_once()

    async def test_a_web_page_model_with_no_document_uri_is_refused_by_name(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker, is_web_page_supported=True)

        with pytest.raises(ExtractInputError, match="document_uri"):
            await worker._extract_pages(_make_extract_job(mocker, image_uri="file:///local/scan.png"))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

    async def test_no_input_at_all_is_refused(self, mocker: MockerFixture) -> None:
        worker = _make_worker(mocker)
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")

        with pytest.raises(ExtractInputError):
            await worker._extract_pages(_make_extract_job(mocker))  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio(loop_scope="class")
class TestManifoldExtractUsageTranslation:
    async def test_pages_become_megatokens_in_both_categories(self, mocker: MockerFixture) -> None:
        """The figure the Portkey path reports for the same work, from a different unit.

        The costume reports `usage.prompt_tokens = pages * 1_000_000`; the native route reports
        `usage.pages = N`. Both must price the same, or phase 4's mixed-profile comparison means
        nothing. Both categories are filled because that is what the abstract worker's own fallback
        produces.
        """
        worker = _make_worker(mocker)
        mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=_PDF_BYTES_URL,
        )
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")
        job = _make_extract_job(mocker, document_uri="/local/report.pdf")
        usage = mocker.MagicMock()
        job.job_report.extract_tokens_usage = usage

        await worker._extract_pages(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert usage.nb_tokens_by_category == {
            TokenCategory.INPUT: 3 * MANIFOLD_UNIT_TOKENS,
            TokenCategory.OUTPUT: 3 * MANIFOLD_UNIT_TOKENS,
        }

    @pytest.mark.parametrize(
        "response_body",
        [
            {"pages": {}},
            {"pages": {}, "usage": None},
            {"pages": {}, "usage": {}},
            {"pages": {}, "usage": {"pages": "three"}},
        ],
        ids=["no-usage", "null-usage", "empty-usage", "non-numeric-pages"],
    )
    async def test_a_usage_block_the_route_did_not_send_leaves_the_abstract_fallback_in_charge(
        self,
        mocker: MockerFixture,
        response_body: dict[str, Any],
    ) -> None:
        """Silence here is correct: `ExtractWorkerAbstract` counts the pages it received instead."""
        worker = _make_worker(mocker, response_body=response_body)
        mocker.patch(
            "pipelex.providers.manifold.manifold_extract_worker.make_base64_url_from_any_uri",
            new_callable=mocker.AsyncMock,
            return_value=_PDF_BYTES_URL,
        )
        mocker.patch("pipelex.providers.manifold.manifold_extract_worker.get_storage_provider")
        job = _make_extract_job(mocker, document_uri="/local/report.pdf")
        usage = mocker.MagicMock()
        empty_categories: NbTokensByCategoryDict = {}
        usage.nb_tokens_by_category = empty_categories
        job.job_report.extract_tokens_usage = usage

        await worker._extract_pages(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert usage.nb_tokens_by_category == {}
