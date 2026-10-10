from collections.abc import Iterator

import pytest

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.runtime_hub import get_class_registry, get_model_deck
from tests.integration.pipelex.pipes.operator.pipe_judge.test_data import ClassBackedOpenTriage, ClassBackedTriage, PipeJudgeLoadTestData


@pytest.fixture
def judgment_model_reading_files() -> Iterator[None]:
    """The judgment model, for one test, as a backend that reads images and PDFs would declare it."""
    judgment_specs = get_model_deck().inference_models.root[ModelType.JUDGMENT]
    booted_spec = judgment_specs[PipeJudgeLoadTestData.JUDGMENT_MODEL]
    judgment_specs[PipeJudgeLoadTestData.JUDGMENT_MODEL] = booted_spec.model_copy(update={"inputs": ["text", "images", "pdf"]})
    try:
        yield
    finally:
        judgment_specs[PipeJudgeLoadTestData.JUDGMENT_MODEL] = booted_spec


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


@pytest.fixture
def unserved_judgment_waterfall() -> Iterator[str]:
    """A judgment waterfall, for one test, whose only model no backend serves: its reference."""
    model_deck = get_model_deck()
    model_deck.judgment_waterfalls["unserved_judges"] = ["jev-0.0.0-unserved"]
    try:
        yield "~unserved_judges"
    finally:
        del model_deck.judgment_waterfalls["unserved_judges"]


@pytest.fixture
def class_backed_triages() -> Iterator[None]:
    """The hand-written triage structure classes, registered for one test so a concept may name them as its structure."""
    class_registry = get_class_registry()
    class_registry.register_class(ClassBackedTriage)
    class_registry.register_class(ClassBackedOpenTriage)
    try:
        yield
    finally:
        class_registry.unregister_class(ClassBackedTriage)
        class_registry.unregister_class(ClassBackedOpenTriage)
