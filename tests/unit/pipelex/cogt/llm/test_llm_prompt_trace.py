import hashlib

from pipelex.cogt.image.prompt_image import PromptImageUri
from pipelex.cogt.llm.llm_prompt import LLMPrompt
from pipelex.cogt.llm.llm_prompt_trace import TRACED_PROMPT_TEXT_MAX_BYTES, LLMPromptTrace, PromptTextPreview


class TestLLMPromptTrace:
    def test_a_text_within_the_bound_comes_back_whole(self) -> None:
        llm_prompt = LLMPrompt(system_text="Be brief.", user_text="Summarize this.", user_images=[PromptImageUri(uri="https://example.com/a.png")])

        trace = LLMPromptTrace.make_from_prompt(llm_prompt=llm_prompt)

        assert trace.system_text == "Be brief."
        assert trace.traced_user_text == "Summarize this."
        assert trace.user_images == llm_prompt.user_images

    def test_a_text_past_the_bound_comes_back_as_its_preview_with_its_size_and_hash(self) -> None:
        # Multi-byte characters straddle the bound, so the cut must not split one.
        user_text = "Read: " + "é" * TRACED_PROMPT_TEXT_MAX_BYTES
        encoded = user_text.encode("utf-8")

        trace = LLMPromptTrace.make_from_prompt(llm_prompt=LLMPrompt(user_text=user_text))

        assert isinstance(trace.user_text, PromptTextPreview)
        assert trace.user_text.size == len(encoded)
        assert trace.user_text.sha256 == hashlib.sha256(encoded).hexdigest()
        assert user_text.startswith(trace.user_text.preview)
        assert len(trace.user_text.preview.encode("utf-8")) <= TRACED_PROMPT_TEXT_MAX_BYTES
        assert len(trace.user_text.preview.encode("utf-8")) > TRACED_PROMPT_TEXT_MAX_BYTES - 2
        assert trace.traced_user_text == f"{trace.user_text.preview}… [cut for the trace: {len(encoded)} bytes, sha256 {trace.user_text.sha256}]"
        assert trace.system_text is None

    def test_the_trace_crosses_as_json(self) -> None:
        trace = LLMPromptTrace.make_from_prompt(llm_prompt=LLMPrompt(system_text="Be brief.", user_text="x" * 40), max_text_bytes=16)

        crossed = LLMPromptTrace.model_validate_json(trace.model_dump_json())

        assert crossed == trace
        assert isinstance(crossed.user_text, PromptTextPreview)
        assert crossed.system_text == "Be brief."
