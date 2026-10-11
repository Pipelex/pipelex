from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
import typer
from openai import AsyncOpenAI
from rich.console import Console

from pipelex.cli.commands.run._run_core import _execute_run  # pyright: ignore[reportPrivateUsage]
from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.providers.openai.openai_completions_factory import OpenAICompletionsFactory
from pipelex.providers.openai.openai_completions_llm_worker import OpenAICompletionsLLMWorker
from tests.integration.pipelex.cli.test_data import TruncatedCompletionRunTestData

if TYPE_CHECKING:
    from pathlib import Path

    from pytest_mock import MockerFixture


def _truncating_worker() -> OpenAICompletionsLLMWorker:
    """A real chat-completions worker whose provider answers every call with a text cut at its output limit."""
    body: dict[str, Any] = {
        "id": "chatcmpl_truncated",
        "object": "chat.completion",
        "created": 0,
        "model": "stand-in-gpt-1",
        "choices": [
            {"index": 0, "finish_reason": "length", "message": {"role": "assistant", "content": TruncatedCompletionRunTestData.PARTIAL_TEXT}}
        ],
        "usage": {"prompt_tokens": 12, "completion_tokens": 64, "total_tokens": 76},
    }

    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body, request=request)

    sdk_client = AsyncOpenAI(
        api_key="test-key",
        base_url="https://provider.test/v1",
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(answer)),
    )
    inference_model = InferenceModelSpec(
        backend_name="stand_in",
        name=TruncatedCompletionRunTestData.MODEL_HANDLE,
        sdk="openai",
        model_type=ModelType.LLM,
        model_id="stand-in-gpt-1",
        inputs=["text"],
        outputs=["text", "structured"],
        costs={},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )
    return OpenAICompletionsLLMWorker(
        openai_completions_factory=OpenAICompletionsFactory(is_http_url_enabled=False),
        sdk_instance=sdk_client,
        inference_model=inference_model,
        reporting_delegate=None,
    )


@pytest.mark.asyncio(loop_scope="class")
class TestRunTruncatedCompletion:
    async def test_a_truncated_text_fails_the_run_naming_the_pipe_and_the_error(
        self,
        mocker: MockerFixture,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """`pipelex run` on a step whose completion stops at its limit exits non-zero, naming the pipe and the truncation, and prints no output."""
        mocker.patch("pipelex.cogt.content_generation.llm_generate.get_llm_worker", return_value=_truncating_worker())
        console = Console(width=400, record=True, color_system=None)
        mocker.patch("pipelex.cli.error_handlers.get_console", return_value=console)
        mocker.patch("pipelex.cli.commands.run._run_core.get_console", return_value=console)
        bundle_path = tmp_path / "truncated_completion.mthds"
        bundle_path.write_text(TruncatedCompletionRunTestData.MTHDS, encoding="utf-8")

        with pytest.raises(typer.Exit) as exit_info:
            await _execute_run(
                pipe_code=TruncatedCompletionRunTestData.PIPE_CODE,
                bundle_path=str(bundle_path),
                inputs='{"topic": "cats"}',
                save_working_memory=False,
                working_memory_path=None,
                save_main_stuff=False,
                no_pretty_print=True,
                graph=False,
                graph_full_data=None,
                output_dir=str(tmp_path / "outputs"),
                dry_run=False,
                mock_usage=False,
                mock_inputs=False,
                library_dir=None,
            )

        assert exit_info.value.exit_code == 1
        stderr = capsys.readouterr().err
        pipe_code = TruncatedCompletionRunTestData.PIPE_CODE
        model_handle = TruncatedCompletionRunTestData.MODEL_HANDLE
        assert f"Failed to execute pipeline '{pipe_code}': Pipe '{pipe_code}' failed: " in stderr
        assert (
            f"The model '{model_handle}' was cut off before it finished the text of pipe '{pipe_code}' "
            "(stop reason 'length', 64 output tokens used, no max_tokens sent), so the text is incomplete. "
            "Set the pipe's max_tokens up to the model's limit, lower its reasoning effort, or shorten its input."
        ) in stderr
        assert TruncatedCompletionRunTestData.PARTIAL_TEXT not in stderr
        assert TruncatedCompletionRunTestData.PARTIAL_TEXT not in console.export_text()
