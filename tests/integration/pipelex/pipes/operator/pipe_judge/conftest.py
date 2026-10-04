from collections.abc import Iterator

import pytest

from pipelex.runtime_hub import get_model_deck
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import PipeJudgeLoadTestData


@pytest.fixture
def judgment_model_reading_files() -> Iterator[None]:
    """The judgment model, for one test, as a backend that reads images and PDFs would declare it."""
    model_deck = get_model_deck()
    booted_spec = model_deck.inference_models[PipeJudgeLoadTestData.JUDGMENT_MODEL]
    model_deck.inference_models[PipeJudgeLoadTestData.JUDGMENT_MODEL] = booted_spec.model_copy(update={"inputs": ["text", "images", "pdf"]})
    try:
        yield
    finally:
        model_deck.inference_models[PipeJudgeLoadTestData.JUDGMENT_MODEL] = booted_spec


@pytest.fixture
def no_judgment_default() -> Iterator[None]:
    """A deck that names no default judgment model, which is the kit's own state, made explicit for one test."""
    model_deck = get_model_deck()
    booted_default = model_deck.judgment_choice_default
    model_deck.judgment_choice_default = None
    try:
        yield
    finally:
        model_deck.judgment_choice_default = booted_default
