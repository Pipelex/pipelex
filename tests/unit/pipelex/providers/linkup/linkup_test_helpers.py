from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pipelex.cogt.llm.thinking_mode import ThinkingMode
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchSetting
from pipelex.cogt.usage.cost_category import CostCategory
from pipelex.providers.linkup.linkup_search_worker import LinkupSearchWorker
from pipelex.system.job_metadata import JobMetadata, RunMetadata

if TYPE_CHECKING:
    from pytest_mock import MockerFixture

    from pipelex.cogt.search.search_job import SearchJob

# Linkup's rate, per million tokens, which prices one request since a request is recorded as a million tokens.
LINKUP_REQUEST_RATE = 0.005
LINKUP_SEARCH_MODEL = "linkup-standard"


def linkup_model(*, model_type: ModelType, name: str, model_id: str, inputs: list[str], outputs: list[str]) -> InferenceModelSpec:
    """A Linkup model priced at Linkup's request rate."""
    return InferenceModelSpec(
        backend_name="linkup",
        name=name,
        sdk="linkup",
        model_type=model_type,
        model_id=model_id,
        inputs=inputs,
        outputs=outputs,
        costs={CostCategory.INPUT: LINKUP_REQUEST_RATE, CostCategory.OUTPUT: 0.0},
        thinking_mode=ThinkingMode.NONE,
        max_tokens=None,
        max_prompt_images=None,
    )


def linkup_job_metadata() -> JobMetadata:
    return JobMetadata(
        run_metadata=RunMetadata(user_id="pytest", storage_scope="test/scope", read_scope=None, pipeline_run_id="plr-linkup"),
        pipe_code="some_pipe",
    )


def linkup_search_worker(mocker: MockerFixture, *, response: Any) -> LinkupSearchWorker:
    """A Linkup search worker whose SDK client is mocked to answer every search with `response`, so no provider is called."""
    linkup_client = mocker.patch("pipelex.providers.linkup.linkup_search_worker.LinkupClient").return_value
    linkup_client.async_search = mocker.AsyncMock(return_value=response)
    model = linkup_model(
        model_type=ModelType.SEARCH,
        name=LINKUP_SEARCH_MODEL,
        model_id="standard",
        inputs=["text"],
        outputs=["sourced-answers", "structured"],
    )
    return LinkupSearchWorker(inference_model=model, api_key="test-key")


def linkup_search_job(*, query: str) -> SearchJob:
    return SearchJobFactory.make_search_job(query, search_setting=SearchSetting(model=LINKUP_SEARCH_MODEL), job_metadata=linkup_job_metadata())
