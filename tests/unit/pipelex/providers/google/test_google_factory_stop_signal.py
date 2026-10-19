from __future__ import annotations

from typing import Any

import pytest
from google.genai import types as genai_types

from pipelex.providers.google.google_factory import GeminiStopSignal, GoogleFactory

# Gemini answers as its API sends them, read by the genai SDK as the workers receive them.
_STOP_SIGNAL_CASES: list[Any] = [
    pytest.param(
        {"candidates": [{"finishReason": "IMAGE_SAFETY", "index": 0}]},
        GeminiStopSignal(finish_reason="IMAGE_SAFETY", block_reason=None),
        id="candidate-with-finish-reason",
    ),
    pytest.param(
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "Hello."}]}, "index": 0}]},
        GeminiStopSignal(finish_reason=None, block_reason=None),
        id="candidate-without-finish-reason",
    ),
    pytest.param(
        {"promptFeedback": {"blockReason": "PROHIBITED_CONTENT"}},
        GeminiStopSignal(finish_reason=None, block_reason="PROHIBITED_CONTENT"),
        id="blocked-prompt",
    ),
    # The block reason is read only when no candidate came back, the two vocabularies sharing words with other meanings
    pytest.param(
        {"candidates": [{"finishReason": "STOP", "index": 0}], "promptFeedback": {"blockReason": "SAFETY"}},
        GeminiStopSignal(finish_reason="STOP", block_reason=None),
        id="candidate-and-prompt-feedback",
    ),
    pytest.param({}, GeminiStopSignal(finish_reason=None, block_reason=None), id="no-candidate-and-no-feedback"),
]


class TestGoogleFactoryStopSignal:
    @pytest.mark.parametrize(("answer", "expected_signal"), _STOP_SIGNAL_CASES)
    def test_the_answer_says_how_it_stopped(self, answer: dict[str, Any], expected_signal: GeminiStopSignal) -> None:
        response = genai_types.GenerateContentResponse.model_validate(answer)

        assert GoogleFactory.read_stop_signal(response=response) == expected_signal
