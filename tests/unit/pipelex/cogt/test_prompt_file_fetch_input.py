from collections.abc import Awaitable, Callable

import pytest
from mthds.protocol.problem.registry import CoreCode
from pytest_mock import MockerFixture

from pipelex.cogt.document import prompt_document_utils
from pipelex.cogt.document.prompt_document_factory import PromptDocumentFactory
from pipelex.cogt.document.prompt_document_utils import prepare_prompt_document, prepare_prompt_document_as_base64
from pipelex.cogt.image import prompt_image_utils
from pipelex.cogt.image.prompt_image_factory import PromptImageFactory
from pipelex.cogt.image.prompt_image_utils import prepare_prompt_image, prepare_prompt_image_as_base64
from pipelex.errors.problem import ProblemView
from pipelex.tools.misc.exceptions import RemoteFileFetchError
from pipelex.tools.misc.file_fetch_utils import fetching_for_input

# The URL of a caller's input, which no message names.
_URL = "https://files.example.com/jane-doe-scan.png"


def _unreachable() -> RemoteFileFetchError:
    return RemoteFileFetchError("Could not fetch a remote file: the server did not answer", host="files.example.com").with_error_code(
        CoreCode.INPUT_URL_UNREACHABLE
    )


async def _prepare_image(*, input_name: str | None) -> object:
    return await prepare_prompt_image(PromptImageFactory.make_prompt_image(uri=_URL, input_name=input_name), is_http_url_enabled=False)


async def _prepare_image_as_base64(*, input_name: str | None) -> object:
    return await prepare_prompt_image_as_base64(PromptImageFactory.make_prompt_image(uri=_URL, input_name=input_name))


async def _prepare_document(*, input_name: str | None) -> object:
    return await prepare_prompt_document(PromptDocumentFactory.make_prompt_document(uri=_URL, input_name=input_name), is_http_url_enabled=False)


async def _prepare_document_as_base64(*, input_name: str | None) -> object:
    return await prepare_prompt_document_as_base64(PromptDocumentFactory.make_prompt_document(uri=_URL, input_name=input_name))


@pytest.mark.asyncio(loop_scope="class")
class TestPromptFileFetchInput:
    @pytest.mark.parametrize(
        "prepare",
        [_prepare_image, _prepare_image_as_base64, _prepare_document, _prepare_document_as_base64],
        ids=["image", "image_as_base64", "document", "document_as_base64"],
    )
    async def test_a_failed_fetch_names_the_input_the_prompt_read_it_from(
        self, mocker: MockerFixture, prepare: Callable[..., Awaitable[object]]
    ) -> None:
        """A prompt's image or document fetched from its URL: the failure names the input, never the URL."""
        for module in (prompt_image_utils, prompt_document_utils):
            mocker.patch.object(module, "fetch_file_from_url_httpx", side_effect=_unreachable())

        with pytest.raises(RemoteFileFetchError) as exc_info:
            await prepare(input_name="scans[2]")

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.params is not None
        assert caller.params.as_wire() == {"input": "scans[2]", "host": "files.example.com"}
        assert "jane-doe-scan" not in str(caller.to_wire())

    async def test_a_url_no_input_gave_names_no_input(self) -> None:
        with pytest.raises(RemoteFileFetchError) as exc_info, fetching_for_input(input_name=None):
            raise _unreachable()

        assert exc_info.value.input_name is None

    async def test_an_input_already_named_is_kept(self) -> None:
        with pytest.raises(RemoteFileFetchError) as exc_info, fetching_for_input(input_name="outer"):
            raise _unreachable().with_input(input_name="inner")

        assert exc_info.value.input_name == "inner"
