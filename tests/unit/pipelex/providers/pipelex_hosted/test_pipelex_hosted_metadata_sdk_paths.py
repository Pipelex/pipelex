"""Every path the hosted dialect calls the service on carries `x-pipelex-metadata` for its job.

The header differs per job, so it cannot be a client default: each path adds it per request, and
each is pinned here where the request leaves the runtime — the kwargs handed to the SDK call, or the
headers handed to `httpx` on the native routes. The paths are the OpenAI-substrate chat completions
(text, and image generation over completions) and responses, the vendor-SDK image path, the native
extract and search routes, and Claude over the Anthropic worker the package registers as `pipelex_hosted_anthropic`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from anthropic import AsyncAnthropic
from anthropic.types import Message, ToolUseBlock, Usage

from pipelex.cogt.llm.llm_job import LLMJob
from pipelex.cogt.llm.llm_job_components import LLMJobConfig, LLMJobParams, LLMJobReport
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.cogt.model_backends.backend import InferenceBackend, PipelexBackend
from pipelex.providers.anthropic.anthropic_llm_worker import AnthropicLLMWorker
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from pipelex.providers.pipelex_hosted.pipelex_hosted_anthropic_extras import PipelexHostedAnthropicExtrasFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_completions_factory import PipelexHostedCompletionsFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_constants import PIPELEX_HOSTED_METADATA_HEADER
from pipelex.providers.pipelex_hosted.pipelex_hosted_extract_worker import PipelexHostedExtractWorker
from pipelex.providers.pipelex_hosted.pipelex_hosted_img_gen_worker import PipelexHostedImgGenWorker
from pipelex.providers.pipelex_hosted.pipelex_hosted_native_client import PipelexHostedNativeClient
from pipelex.providers.pipelex_hosted.pipelex_hosted_responses_factory import PipelexHostedResponsesFactory
from pipelex.providers.pipelex_hosted.pipelex_hosted_search_worker import PipelexHostedSearchWorker
from tests.helpers.instructor_test_utils import DummySchema
from tests.unit.pipelex.providers.pipelex_hosted.test_data import PipelexHostedMetadataTestData

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

_EXPECTED = {PIPELEX_HOSTED_METADATA_HEADER: PipelexHostedMetadataTestData.EXPECTED_HEADER_VALUE}
_ORIGIN = "https://pipelex_hosted.example.com"


class _RequestCapturedError(Exception):
    """Raised by a stubbed SDK call once it has recorded its arguments, so no response has to be faked."""


def _llm_job() -> LLMJob:
    return LLMJob(
        job_metadata=PipelexHostedMetadataTestData.JOB_METADATA,
        llm_prompt=LLMPrompt(user_text="ping"),
        job_params=LLMJobParams(temperature=0.5),
        job_config=LLMJobConfig(schema_reask_max_attempts=1),
        job_report=LLMJobReport(),
    )


def _model(mocker: MockerFixture, *, backend_name: str = PipelexBackend.PIPELEX_HOSTED, model_id: str = "gpt-4o") -> Any:
    model = mocker.MagicMock()
    model.desc = "test-model-desc"
    model.model_id = model_id
    model.name = model_id
    model.backend_name = backend_name
    model.thinking_mode = None
    model.listed_constraints = []
    model.extra_headers = None
    return model


def _native_client() -> PipelexHostedNativeClient:
    return PipelexHostedNativeClient(backend=InferenceBackend(name="pipelex_hosted", endpoint=_ORIGIN, api_key="token"))


def _patch_httpx_post(mocker: MockerFixture, *, json_body: dict[str, Any]) -> Any:
    response = httpx.Response(status_code=200, request=httpx.Request("POST", _ORIGIN), json=json_body)
    return mocker.patch.object(httpx.AsyncClient, "post", new_callable=mocker.AsyncMock, return_value=response)


def _anthropic_worker(mocker: MockerFixture, *, sdk_client: AsyncAnthropic, backend_name: str) -> AnthropicLLMWorker:
    from instructor import from_anthropic  # ruff: ignore[import-outside-top-level]

    worker = object.__new__(AnthropicLLMWorker)
    model = _model(mocker, backend_name=backend_name, model_id="claude-test")
    model.structure_method = StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS
    worker.inference_model = model
    worker.extras_factory = PipelexHostedAnthropicExtrasFactory()
    worker.default_max_tokens = 4096
    worker.instructor_for_objects = from_anthropic(client=sdk_client, mode=StructureMethod.INSTRUCTOR_ANTHROPIC_TOOLS.as_instructor_mode())
    config = mocker.MagicMock()
    config.inference.llm.anthropic.structured_output_timeout_seconds = 1200
    mocker.patch("pipelex.providers.anthropic.anthropic_llm_worker.get_config", return_value=config)
    return worker


def _tool_call_message() -> Message:
    return Message(
        id="msg_test",
        type="message",
        role="assistant",
        model="claude-test",
        content=[ToolUseBlock(type="tool_use", id="toolu_test", name="DummySchema", input={"text": "answer"})],
        stop_reason="tool_use",
        stop_sequence=None,
        usage=Usage(input_tokens=1, output_tokens=1),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestPipelexHostedMetadataSdkPaths:
    @pytest.mark.parametrize(
        "factory",
        [PipelexHostedCompletionsFactory(is_http_url_enabled=False), PipelexHostedResponsesFactory(is_http_url_enabled=False)],
        ids=["completions", "responses"],
    )
    async def test_the_openai_substrate_extras_carry_the_header(self, mocker: MockerFixture, factory: Any) -> None:
        """`make_extras` feeds every OpenAI-substrate call: completions text and objects, image gen over completions, responses."""
        extra_headers, _ = factory.make_extras(inference_model=_model(mocker), inference_job=_llm_job(), output_desc="text")

        assert extra_headers == _EXPECTED

    async def test_a_catalog_header_of_the_same_name_does_not_override_the_job(self, mocker: MockerFixture) -> None:
        model = _model(mocker)
        model.extra_headers = {"anthropic-beta": "some-beta", PIPELEX_HOSTED_METADATA_HEADER: '{"user_id":"catalog"}'}

        extra_headers, _ = PipelexHostedCompletionsFactory(is_http_url_enabled=False).make_extras(
            inference_model=model, inference_job=_llm_job(), output_desc="text"
        )

        assert extra_headers == {"anthropic-beta": "some-beta", **_EXPECTED}

    async def test_the_completions_worker_sends_the_header_on_the_sdk_call(self, mocker: MockerFixture) -> None:
        worker = object.__new__(OpenAICompletionsLLMWorker)
        worker.inference_model = _model(mocker)
        worker.openai_completions_factory = PipelexHostedCompletionsFactory(is_http_url_enabled=False)
        client = mocker.MagicMock()
        client.chat.completions.create = mocker.AsyncMock(side_effect=_RequestCapturedError)
        worker.openai_client_for_text = client

        with pytest.raises(_RequestCapturedError):
            await worker._gen_text(_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert client.chat.completions.create.call_args.kwargs["extra_headers"] == _EXPECTED

    @pytest.mark.parametrize(
        ("args", "route"),
        [({"prompt": "draw"}, "generate"), ({"prompt": "edit", "image": [("a.png", b"\x89PNG", "image/png")]}, "edit")],
        ids=["generate", "edit"],
    )
    async def test_the_image_worker_sends_the_header_on_both_images_routes(self, mocker: MockerFixture, args: dict[str, Any], route: str) -> None:
        worker = object.__new__(PipelexHostedImgGenWorker)
        worker.inference_model = _model(mocker, model_id="gpt-image-1")
        client: Any = mocker.MagicMock()
        client.images.generate = mocker.AsyncMock(side_effect=_RequestCapturedError)
        client.images.edit = mocker.AsyncMock(side_effect=_RequestCapturedError)
        worker.portkey_client = client
        mocker.patch(
            "pipelex.providers.pipelex_hosted.pipelex_hosted_img_gen_worker.ImgGenArgsFactory.make_args_for_model",
            new_callable=mocker.AsyncMock,
            return_value=args,
        )
        job = mocker.MagicMock()
        job.job_metadata = PipelexHostedMetadataTestData.JOB_METADATA

        with pytest.raises(_RequestCapturedError):
            await worker._gen_image_list(img_gen_job=job, nb_images=1)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert getattr(client.images, route).call_args.kwargs["extra_headers"] == _EXPECTED

    async def test_the_extract_route_sends_the_header_on_the_wire(self, mocker: MockerFixture) -> None:
        post = _patch_httpx_post(mocker, json_body={"pages": {}})
        worker = object.__new__(PipelexHostedExtractWorker)
        model = _model(mocker, model_id="firecrawl/scrape")
        model.is_web_page_supported_for_extract = True
        worker.inference_model = model
        worker.client = _native_client()
        job = mocker.MagicMock()
        job.job_metadata = PipelexHostedMetadataTestData.JOB_METADATA
        job.extract_input.document_uri = "https://example.com/page"
        job.job_params.max_nb_images = None
        job.job_params.render_js = None
        job.job_params.include_raw_html = None
        job.job_report.extract_tokens_usage = None

        await worker._extract_pages(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert post.call_args.kwargs["headers"][PIPELEX_HOSTED_METADATA_HEADER] == PipelexHostedMetadataTestData.EXPECTED_HEADER_VALUE

    async def test_the_search_route_sends_the_header_on_the_wire(self, mocker: MockerFixture) -> None:
        post = _patch_httpx_post(mocker, json_body={"answer": "a torus is a surface", "sources": []})
        worker = object.__new__(PipelexHostedSearchWorker)
        worker.inference_model = _model(mocker, model_id="linkup/standard")
        worker.client = _native_client()
        job = mocker.MagicMock()
        job.job_metadata = PipelexHostedMetadataTestData.JOB_METADATA
        job.query = "what is a torus"
        job.job_params.search_setting.include_images = False
        job.job_params.search_setting.include_inline_citations = False
        job.job_params.search_setting.max_results = 10
        job.job_params.include_domains = None
        job.job_params.exclude_domains = None
        job.job_params.from_date = None
        job.job_params.to_date = None
        job.job_report.search_tokens_usage = None

        await worker._search_sourced_answer(job)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert post.call_args.kwargs["headers"][PIPELEX_HOSTED_METADATA_HEADER] == PipelexHostedMetadataTestData.EXPECTED_HEADER_VALUE

    async def test_claude_behind_pipelex_hosted_sends_the_header_on_the_text_call(self, mocker: MockerFixture) -> None:
        sdk_client = AsyncAnthropic(api_key="test-key")
        stream = mocker.MagicMock(side_effect=_RequestCapturedError)
        mocker.patch.object(sdk_client.messages, "stream", new=stream)
        worker = _anthropic_worker(mocker, sdk_client=sdk_client, backend_name=PipelexBackend.PIPELEX_HOSTED)
        worker.anthropic_async_client = sdk_client

        with pytest.raises(_RequestCapturedError):
            await worker._gen_text(_llm_job())  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        assert stream.call_args.kwargs["extra_headers"] == _EXPECTED

    async def test_claude_behind_pipelex_hosted_sends_the_header_on_the_structured_call(self, mocker: MockerFixture) -> None:
        """Through a real instructor client, so what is asserted is what reaches the SDK's `messages.create`."""
        sdk_client = AsyncAnthropic(api_key="test-key")
        create = mocker.AsyncMock(return_value=_tool_call_message())
        mocker.patch.object(sdk_client.messages, "create", new=create)
        worker = _anthropic_worker(mocker, sdk_client=sdk_client, backend_name=PipelexBackend.PIPELEX_HOSTED)

        await worker._gen_object(_llm_job(), schema=DummySchema)  # ruff: ignore[private-member-access]  # pyright: ignore[reportPrivateUsage]

        await_args = create.await_args
        assert await_args is not None
        assert await_args.kwargs["extra_headers"] == _EXPECTED
