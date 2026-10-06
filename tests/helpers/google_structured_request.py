"""Fakes for driving the Google LLM worker's structured call through a real instructor client.

``_gen_object`` goes through instructor's genai handlers, which build the Google ``GenerateContentConfig``
themselves from the kwargs they recognise and silently drop the rest. The worker is built over a real
``from_genai`` client whose ``generate_content`` captures what reaches it, so a test asserts what is actually sent.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from google import genai
from google.genai import types as genai_types
from instructor import from_genai

from pipelex.cogt.llm.structured_output import StructureMethod
from pipelex.providers.google.google_config import GoogleConfig
from pipelex.providers.google.google_llm_worker import GoogleLLMWorker
from tests.helpers.instructor_test_utils import DummySchema

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.llm.thinking_mode import ThinkingMode

GOOGLE_LEVEL_MAP: dict[str, str] = {
    "none": "disabled",
    "minimal": "minimal",
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "high",
    "max": "high",
}
GEMINI_BUDGET_MAP: dict[str, int] = {"none": 0, "minimal": 512, "low": 1024, "medium": 5000, "high": 16384, "xhigh": 32768, "max": 65536}
GENAI_STRUCTURE_METHODS = [StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS, StructureMethod.INSTRUCTOR_GENAI_TOOLS]


def gemini_budget(*, family: str, effort: str) -> int:
    assert family == "gemini"
    return GEMINI_BUDGET_MAP[effort]


def make_response(*, structure_method: StructureMethod, schema_name: str, payload: dict[str, Any]) -> genai_types.GenerateContentResponse:
    match structure_method:
        case StructureMethod.INSTRUCTOR_GENAI_TOOLS:
            part = genai_types.Part(function_call=genai_types.FunctionCall(name=schema_name, args=payload))
        case StructureMethod.INSTRUCTOR_GENAI_STRUCTURED_OUTPUTS:
            part = genai_types.Part(text=json.dumps(payload))
        case _:
            msg = f"No Gemini response shape for {structure_method}"
            raise ValueError(msg)
    return genai_types.GenerateContentResponse(candidates=[genai_types.Candidate(content=genai_types.Content(role="model", parts=[part]))])


def make_structured_worker(
    mocker: MockerFixture,
    *,
    structure_method: StructureMethod,
    captured: dict[str, Any],
    schema_name: str = DummySchema.__name__,
    payload: dict[str, Any] | None = None,
    thinking_mode: ThinkingMode | None = None,
    min_thinking_budget: int | None = None,
    max_thinking_budget: int | None = None,
) -> GoogleLLMWorker:
    """A worker over a real instructor client whose ``generate_content`` records what reaches it in ``captured``."""
    client = genai.Client(api_key="test-key")
    response_payload = payload or {"text": "ok"}

    # The real keyword-only signature, so a keyword `generate_content` does not take fails here as it does live
    def fake_generate_content(
        *, model: str, contents: Any, config: genai_types.GenerateContentConfig | None = None
    ) -> genai_types.GenerateContentResponse:
        captured.update(model=model, contents=contents, config=config)
        return make_response(structure_method=structure_method, schema_name=schema_name, payload=response_payload)

    mocker.patch.object(client.aio.models, "generate_content", new_callable=mocker.AsyncMock, side_effect=fake_generate_content)

    worker = object.__new__(GoogleLLMWorker)
    mock_model = mocker.MagicMock()
    mock_model.desc = "test-model-desc"
    mock_model.model_id = "gemini-pro"
    mock_model.name = "gemini-pro"
    mock_model.thinking_mode = thinking_mode
    mock_model.min_thinking_budget = min_thinking_budget
    mock_model.max_thinking_budget = max_thinking_budget
    worker.inference_model = mock_model
    worker.instructor_for_objects = from_genai(client=client, mode=structure_method.as_instructor_mode(), use_async=True)

    config = mocker.MagicMock()
    config.inference.llm.google = GoogleConfig(effort_to_level_map=GOOGLE_LEVEL_MAP)
    config.inference.llm.get_reasoning_budget = mocker.MagicMock(side_effect=gemini_budget)
    mocker.patch("pipelex.providers.google.google_llm_worker.get_config", return_value=config)
    return worker
