"""Unit tests for input_normalizer URL handling.

Regression coverage for the hosted-runner 500 (2026-06-11): a DocumentContent
with a blank url resolved as local path '', `Path('')` became `'.'`, and the
uncaught `IsADirectoryError` escaped as an InternalServerError. Both the blank
url and any unreadable local path must surface as the INPUT-domain
`PipelineInputContentError` (→ 422 at the API layer), never a sanitized 500.

Every message of the family is the operator's diagnostics: the caller reads its
code's sentence and the step to change its input. The unreadable-path arm's
message names the resolved path and the OSError subclass, which must never reach
the caller.
"""

from pathlib import Path

import pytest
from mthds.protocol.problem.registry import CoreCode, ProblemDomain, StepKind
from pytest_mock import MockerFixture

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.errors.problem import ProblemView
from pipelex.pipeline.exceptions import PipelineInputContentError, PipelineInputUrlInvalidError, PipelineInputUrlMissingError
from pipelex.pipeline.input_normalizer import prepare_file_inputs
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract


def _memory_with_document(url: str) -> WorkingMemory:
    stuff = StuffFactory.make_stuff(
        concept=ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.DOCUMENT),
        content=DocumentContent(url=url),
        name="document",
    )
    return WorkingMemoryFactory.make_from_single_stuff(stuff)


def _patch_storage_and_config(mocker: MockerFixture) -> None:
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_storage_provider",
        return_value=mocker.Mock(spec=StorageProviderAbstract),
    )
    mocker.patch(
        "pipelex.pipeline.input_normalizer.get_config",
        return_value=mocker.Mock(runtime=mocker.Mock(storage=mocker.Mock(is_upload_local_content_enabled=True))),
    )


@pytest.mark.asyncio(loop_scope="class")
class TestInputNormalizerUrlGuards:
    @pytest.mark.parametrize("blank_url", ["", "   "])
    async def test_blank_url_raises_input_error(self, mocker: MockerFixture, blank_url: str) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputUrlMissingError, match="blank url"):
            await prepare_file_inputs(_memory_with_document(blank_url), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True)

    @pytest.mark.parametrize("bad_url", ["https://", "https://exa mple.com/file.pdf"])
    async def test_malformed_http_url_raises_an_input_error_the_caller_can_fix(self, mocker: MockerFixture, bad_url: str) -> None:
        """A malformed http(s) url is refused at shaping time as the caller's input to change; its message is the operator's."""
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputUrlInvalidError) as exc_info:
            await prepare_file_inputs(_memory_with_document(bad_url), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True)

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_INVALID
        assert caller.next_step.kind == StepKind.CHANGE_INPUT
        assert "not a valid http(s) URL" in exc_info.value.message

    async def test_well_formed_http_url_passes_through_unchanged(self, mocker: MockerFixture) -> None:
        """A well-formed http(s) url is not fetched or probed at shaping time, and it becomes its own public_url."""
        _patch_storage_and_config(mocker)
        mock_get = mocker.patch("httpx.AsyncClient.get")

        memory = await prepare_file_inputs(
            _memory_with_document("https://example.com/file.pdf"), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True
        )

        content = memory.get_stuff("document").content
        assert isinstance(content, DocumentContent)
        assert content.url == "https://example.com/file.pdf"
        assert content.public_url == "https://example.com/file.pdf"
        mock_get.assert_not_called()

    async def test_blank_url_is_the_caller_s_input_to_change(self, mocker: MockerFixture) -> None:
        """A caller who simply forgot a url is told it is its own input to change, never that the runtime failed."""
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputUrlMissingError) as exc_info:
            await prepare_file_inputs(_memory_with_document(""), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True)

        caller = exc_info.value.to_problem(view=ProblemView.CALLER)
        assert caller.code == CoreCode.INPUT_INVALID
        assert caller.domain == ProblemDomain.INPUT
        assert caller.next_step.kind == StepKind.CHANGE_INPUT
        assert "blank url" in exc_info.value.message

    async def test_unreadable_path_message_never_reaches_the_caller(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """The unreadable-path message must NOT reach a caller: it is the operator's diagnostics alone.

        It names the resolved path and the OSError subclass that rejected it. Letting
        those through would answer "does this server-side path exist, and may the runner
        read it?" — ``PermissionError`` on an existing path reads differently from
        ``FileNotFoundError`` on one that does not — for any authenticated caller of a
        deployment that leaves ``is_upload_local_content_enabled`` on.
        """
        _patch_storage_and_config(mocker)
        missing_path = tmp_path / "nope.pdf"

        with pytest.raises(PipelineInputContentError) as exc_info:
            await prepare_file_inputs(
                _memory_with_document(str(missing_path)), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True
            )

        operator = exc_info.value.to_problem(view=ProblemView.OPERATOR)
        assert operator.diagnostics is not None
        assert str(missing_path) in operator.diagnostics.message, "precondition: the raw message carries the path"
        caller_wire = str(exc_info.value.to_problem(view=ProblemView.CALLER).to_wire())
        assert str(missing_path) not in caller_wire
        assert "FileNotFoundError" not in caller_wire

    async def test_directory_path_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A local path that IS a directory must be an input error, not an
        escaped IsADirectoryError (the '.'-as-url production failure mode).
        """
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await prepare_file_inputs(_memory_with_document(str(tmp_path)), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True)

    async def test_path_with_null_byte_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        """A NUL byte makes the path unusable: the read raises ValueError, not OSError, and it must still be an input error."""
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await prepare_file_inputs(
                _memory_with_document(f"{tmp_path}/a\x00b.pdf"), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True
            )

    async def test_missing_file_raises_input_error(self, mocker: MockerFixture, tmp_path: Path) -> None:
        _patch_storage_and_config(mocker)

        with pytest.raises(PipelineInputContentError, match="cannot be read"):
            await prepare_file_inputs(
                _memory_with_document(str(tmp_path / "nope.pdf")), storage_scope="test/scope", read_scope=None, is_relocation_enabled=True
            )
