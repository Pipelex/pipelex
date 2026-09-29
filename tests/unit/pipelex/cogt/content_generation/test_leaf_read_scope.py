"""Every content-generation leaf authorizes the URLs its assignment reads, before the dry-run branch.

On a scoped run a leaf refuses a storage key outside the read scope and a local path, and reads an
in-scope key; it does so in dry mode as well, so a dry run refuses the method a live run would and
these tests need no inference. The raw provider leaves authorize too, for a caller that reaches them
directly, and every refusal happens before a worker is built.
"""

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.cogt.content_generation.assignment_models import (
    ExtractAssignment,
    ImgGenAssignment,
    LLMAssignment,
    ObjectAssignment,
    RenderPageViewsAssignment,
)
from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.extract_generate import extract_gen_pages, extract_gen_pages_and_store
from pipelex.cogt.content_generation.img_gen_generate import (
    img_gen_image_list,
    img_gen_image_list_and_store,
    img_gen_single_image,
    img_gen_single_image_and_store,
)
from pipelex.cogt.content_generation.llm_generate import llm_gen_object, llm_gen_object_list, llm_gen_text
from pipelex.cogt.content_generation.render_generate import render_page_views_and_store
from pipelex.cogt.document.prompt_document import PromptDocumentUri
from pipelex.cogt.extract.extract_input import ExtractInput
from pipelex.cogt.extract.extract_job_components import ExtractJobConfig, ExtractJobParams
from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.img_gen.img_gen_job_components import AspectRatio, Background, ImgGenJobConfig, ImgGenJobParams
from pipelex.cogt.img_gen.img_gen_prompt import ImgGenPrompt
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.uri.exceptions import UriReadRefusalReason, UriReadRefusedError

READ_SCOPE = "org_abc"
IN_SCOPE_IMAGE = "pipelex-storage://org_abc/assets/photo.png"
IN_SCOPE_DOCUMENT = "pipelex-storage://org_abc/assets/report.pdf"
FOREIGN_KEY = "pipelex-storage://org_other/assets/secret.pdf"
LOCAL_PATH = "/etc/passwd"
PIPE_CODE = "describe_photo"


class Summary(BaseModel):
    title: str


def _job_metadata() -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope="org_abc/mt_1/run_1", read_scope=READ_SCOPE),
        pipe_code=PIPE_CODE,
    )


def _llm_assignment(*, run_mode: PipeRunMode, image_uri: str | None = None, document_uri: str | None = None) -> LLMAssignment:
    return LLMAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=run_mode),
        llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
        llm_prompt=LLMPrompt(
            user_text="Describe it.",
            user_images=[PromptImageUri(uri=image_uri)] if image_uri is not None else [],
            user_documents=[PromptDocumentUri(uri=document_uri)] if document_uri is not None else [],
        ),
    )


def _img_gen_assignment(*, run_mode: PipeRunMode, image_uri: str) -> ImgGenAssignment:
    return ImgGenAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=run_mode),
        img_gen_handle="mock-img-gen-handle",
        img_gen_prompt=ImgGenPrompt(positive_text="a red apple", input_images=[PromptImageUri(uri=image_uri)]),
        img_gen_job_params=ImgGenJobParams(aspect_ratio=AspectRatio.SQUARE, background=Background.AUTO),
        img_gen_job_config=ImgGenJobConfig(is_sync_mode=True),
        nb_images=2,
    )


def _extract_assignment(*, run_mode: PipeRunMode, document_uri: str) -> ExtractAssignment:
    return ExtractAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=run_mode),
        extract_handle="mock-extract-handle",
        extract_input=ExtractInput(document_uri=document_uri),
        extract_job_params=ExtractJobParams.make_default_extract_job_params(),
        extract_job_config=ExtractJobConfig(),
    )


def _render_assignment(*, run_mode: PipeRunMode, document_uri: str) -> RenderPageViewsAssignment:
    return RenderPageViewsAssignment(
        job_metadata=_job_metadata(),
        cogt_run_params=CogtRunParams(run_mode=run_mode),
        document_uri=document_uri,
        page_views_dpi=72,
    )


# Each case: a leaf called with an assignment reading the given URI in the given mode.
LeafCall = Callable[[str, PipeRunMode, Any], Awaitable[Any]]


async def _call_llm_text_with_image(uri: str, run_mode: PipeRunMode, _factory: Any) -> Any:
    return await llm_gen_text(llm_assignment=_llm_assignment(run_mode=run_mode, image_uri=uri))


async def _call_llm_text_with_document(uri: str, run_mode: PipeRunMode, _factory: Any) -> Any:
    return await llm_gen_text(llm_assignment=_llm_assignment(run_mode=run_mode, document_uri=uri))


async def _call_llm_object(uri: str, run_mode: PipeRunMode, _factory: Any) -> Any:
    object_assignment = ObjectAssignment.make_for_class(Summary, llm_assignment=_llm_assignment(run_mode=run_mode, document_uri=uri))
    return await llm_gen_object(object_assignment=object_assignment, object_class=Summary)


async def _call_llm_object_list(uri: str, run_mode: PipeRunMode, _factory: Any) -> Any:
    object_assignment = ObjectAssignment.make_for_class(Summary, llm_assignment=_llm_assignment(run_mode=run_mode, image_uri=uri), nb_items=2)
    return await llm_gen_object_list(object_assignment=object_assignment, object_class=Summary)


async def _call_img_gen_single_and_store(uri: str, run_mode: PipeRunMode, factory: Any) -> Any:
    return await img_gen_single_image_and_store(
        img_gen_assignment=_img_gen_assignment(run_mode=run_mode, image_uri=uri), generated_content_factory=factory
    )


async def _call_img_gen_list_and_store(uri: str, run_mode: PipeRunMode, factory: Any) -> Any:
    return await img_gen_image_list_and_store(
        img_gen_assignment=_img_gen_assignment(run_mode=run_mode, image_uri=uri), generated_content_factory=factory
    )


async def _call_extract_and_store(uri: str, run_mode: PipeRunMode, factory: Any) -> Any:
    return await extract_gen_pages_and_store(
        extract_assignment=_extract_assignment(run_mode=run_mode, document_uri=uri), generated_content_factory=factory
    )


async def _call_render_and_store(uri: str, run_mode: PipeRunMode, factory: Any) -> Any:
    return await render_page_views_and_store(
        render_assignment=_render_assignment(run_mode=run_mode, document_uri=uri), generated_content_factory=factory
    )


# The in-scope URI each leaf is given when it should read: an image where the payload is an image.
DRY_LEAVES: list[tuple[str, LeafCall, str]] = [
    ("llm_gen_text with an image", _call_llm_text_with_image, IN_SCOPE_IMAGE),
    ("llm_gen_text with a document", _call_llm_text_with_document, IN_SCOPE_DOCUMENT),
    ("llm_gen_object", _call_llm_object, IN_SCOPE_DOCUMENT),
    ("llm_gen_object_list", _call_llm_object_list, IN_SCOPE_IMAGE),
    ("img_gen_single_image_and_store", _call_img_gen_single_and_store, IN_SCOPE_IMAGE),
    ("img_gen_image_list_and_store", _call_img_gen_list_and_store, IN_SCOPE_IMAGE),
    ("extract_gen_pages_and_store", _call_extract_and_store, IN_SCOPE_DOCUMENT),
    ("render_page_views_and_store", _call_render_and_store, IN_SCOPE_DOCUMENT),
]


@pytest.fixture
def no_workers(mocker: MockerFixture) -> dict[str, Any]:
    """Spy on every worker lookup and silence the dry leaves' usage reporting."""
    mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mocker.MagicMock())
    return {
        "llm": mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker"),
        "img_gen": mocker.patch("pipelex.cogt.content_generation.img_gen_generate.get_img_gen_worker"),
        "extract": mocker.patch("pipelex.cogt.content_generation.extract_generate.get_extract_worker"),
    }


class TestLeavesAuthorizeBeforeTheDryBranch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("leaf_name", "call_leaf", "in_scope_uri"), DRY_LEAVES)
    async def test_a_scoped_dry_run_refuses_a_foreign_key(
        self, mocker: MockerFixture, no_workers: dict[str, Any], leaf_name: str, call_leaf: LeafCall, in_scope_uri: str
    ) -> None:
        del in_scope_uri
        factory = mocker.MagicMock()
        with pytest.raises(UriReadRefusedError) as exc_info:
            await call_leaf(FOREIGN_KEY, PipeRunMode.DRY, factory)
        assert exc_info.value.reason == UriReadRefusalReason.FOREIGN_STORAGE_KEY, leaf_name
        assert f"of pipe '{PIPE_CODE}'" in str(exc_info.value)
        assert factory.method_calls == []
        for worker_spy in no_workers.values():
            worker_spy.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("no_workers")
    @pytest.mark.parametrize(("leaf_name", "call_leaf", "in_scope_uri"), DRY_LEAVES)
    async def test_a_scoped_dry_run_refuses_a_local_path(self, mocker: MockerFixture, leaf_name: str, call_leaf: LeafCall, in_scope_uri: str) -> None:
        del in_scope_uri
        with pytest.raises(UriReadRefusedError) as exc_info:
            await call_leaf(LOCAL_PATH, PipeRunMode.DRY, mocker.MagicMock())
        assert exc_info.value.reason == UriReadRefusalReason.LOCAL_PATH, leaf_name

    @pytest.mark.asyncio
    @pytest.mark.usefixtures("no_workers")
    @pytest.mark.parametrize(("leaf_name", "call_leaf", "in_scope_uri"), DRY_LEAVES)
    async def test_a_scoped_dry_run_reads_an_in_scope_key(
        self, mocker: MockerFixture, leaf_name: str, call_leaf: LeafCall, in_scope_uri: str
    ) -> None:
        result = await call_leaf(in_scope_uri, PipeRunMode.DRY, mocker.MagicMock())
        assert result is not None, leaf_name

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("leaf_name", "call_leaf", "in_scope_uri"), DRY_LEAVES)
    async def test_a_scoped_live_run_refuses_before_building_a_worker(
        self, mocker: MockerFixture, no_workers: dict[str, Any], leaf_name: str, call_leaf: LeafCall, in_scope_uri: str
    ) -> None:
        del in_scope_uri
        with pytest.raises(UriReadRefusedError):
            await call_leaf(FOREIGN_KEY, PipeRunMode.LIVE, mocker.MagicMock())
        for worker_name, worker_spy in no_workers.items():
            assert not worker_spy.called, f"{leaf_name} built a {worker_name} worker before refusing"


class TestRawLeavesAuthorizeToo:
    @pytest.mark.asyncio
    async def test_img_gen_single_image_refuses_a_foreign_key(self, no_workers: dict[str, Any]) -> None:
        with pytest.raises(UriReadRefusedError):
            await img_gen_single_image(img_gen_assignment=_img_gen_assignment(run_mode=PipeRunMode.LIVE, image_uri=FOREIGN_KEY))
        no_workers["img_gen"].assert_not_called()

    @pytest.mark.asyncio
    async def test_img_gen_image_list_refuses_a_local_path(self, no_workers: dict[str, Any]) -> None:
        with pytest.raises(UriReadRefusedError):
            await img_gen_image_list(img_gen_assignment=_img_gen_assignment(run_mode=PipeRunMode.LIVE, image_uri=LOCAL_PATH))
        no_workers["img_gen"].assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_gen_pages_refuses_a_foreign_key(self, no_workers: dict[str, Any]) -> None:
        with pytest.raises(UriReadRefusedError):
            await extract_gen_pages(extract_assignment=_extract_assignment(run_mode=PipeRunMode.LIVE, document_uri=FOREIGN_KEY))
        no_workers["extract"].assert_not_called()


class TestAnUnscopedRunIsUnchanged:
    @pytest.mark.asyncio
    async def test_an_unscoped_dry_run_passes_a_foreign_key_and_a_local_path(self, mocker: MockerFixture) -> None:
        mocker.patch("pipelex.cogt.content_generation.dry_mock.get_report_delegate", return_value=mocker.MagicMock())
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker")
        unscoped_metadata = JobMetadata(
            run_metadata=RunMetadata(user_id="u", pipeline_run_id="run_1", storage_scope="run_1", read_scope=None),
        )
        llm_assignment = LLMAssignment(
            job_metadata=unscoped_metadata,
            cogt_run_params=CogtRunParams(run_mode=PipeRunMode.DRY),
            llm_setting=LLMSetting(model="gpt-4o", temperature=0.5),
            llm_prompt=LLMPrompt(
                user_text="Describe it.",
                user_images=[PromptImageUri(uri=FOREIGN_KEY)],
                user_documents=[PromptDocumentUri(uri=LOCAL_PATH)],
            ),
        )
        result = await llm_gen_text(llm_assignment=llm_assignment)
        assert result.startswith("DRY RUN:")
