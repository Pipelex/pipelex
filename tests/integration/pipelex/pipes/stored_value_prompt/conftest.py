from collections.abc import Generator
from typing import NamedTuple

import pytest
from typing_extensions import override

from pipelex.cogt.content_generation.cogt_run_params import CogtRunParams
from pipelex.cogt.content_generation.content_generator import ContentGenerator
from pipelex.cogt.content_generation.generated_content_factory import GeneratedContentFactory
from pipelex.cogt.llm.llm_generation import LLMObjectGeneration, LLMObjectListGeneration, LLMTextGeneration
from pipelex.cogt.llm.llm_setting import LLMSetting
from pipelex.cogt.llm.unrendered_llm_prompt import UnrenderedLLMPrompt
from pipelex.core.stuffs.stored_value_content import StoredValueContent
from pipelex.core.stuffs.stored_value_walker import find_unloaded_stored_values
from pipelex.runtime_hub import scoped_content_generator
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.typing.pydantic_utils import BaseModelTypeVar
from tests.integration.pipelex.pipes.stored_value_prompt.test_data import READ_SCOPE, STORAGE_SCOPE, STORED_TEXT, STORED_TEXT_KEY


class CrossedPrompt(NamedTuple):
    """What an LLM entry point of the content generator was handed, as it stood when it crossed the protocol."""

    entry_point: str
    wire_dump: str
    context_names: set[str]
    nb_unloaded_stored_values: int
    nb_stored_values: int


class RecordingContentGenerator(ContentGenerator):
    """The in-process generator, recording what crosses its LLM entry points before its leaf loads anything.

    What crosses the protocol is what a host runtime carries across its activity boundary, so it is dumped as JSON
    at the moment of the call: a later look at the arguments would see the values the leaf loaded in place.
    """

    def __init__(self, generated_content_factory: GeneratedContentFactory) -> None:
        super().__init__(generated_content_factory=generated_content_factory)
        self.crossed_prompts: list[CrossedPrompt] = []

    def _record(self, *, entry_point: str, unrendered_prompt: UnrenderedLLMPrompt) -> None:
        stuff_contents = {stuff_name: stuff.content for stuff_name, stuff in unrendered_prompt.context.root.items()}
        nb_stored_values = sum(
            1 for stuff in unrendered_prompt.context.root.values() if isinstance(stuff.content, StoredValueContent) and stuff.content.is_stored
        )
        self.crossed_prompts.append(
            CrossedPrompt(
                entry_point=entry_point,
                wire_dump=unrendered_prompt.model_dump_json(serialize_as_any=True),
                context_names=set(unrendered_prompt.context.root),
                nb_unloaded_stored_values=len(find_unloaded_stored_values(roots=stuff_contents)),
                nb_stored_values=nb_stored_values,
            )
        )

    @override
    async def make_llm_text(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        llm_setting_main: LLMSetting,
        unrendered_prompt: UnrenderedLLMPrompt,
    ) -> LLMTextGeneration:
        self._record(entry_point="make_llm_text", unrendered_prompt=unrendered_prompt)
        return await super().make_llm_text(
            job_metadata=job_metadata, cogt_run_params=cogt_run_params, llm_setting_main=llm_setting_main, unrendered_prompt=unrendered_prompt
        )

    @override
    async def make_object(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object: LLMSetting,
        unrendered_prompt: UnrenderedLLMPrompt,
    ) -> LLMObjectGeneration[BaseModelTypeVar]:
        self._record(entry_point="make_object", unrendered_prompt=unrendered_prompt)
        return await super().make_object(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            object_class=object_class,
            llm_setting_for_object=llm_setting_for_object,
            unrendered_prompt=unrendered_prompt,
        )

    @override
    async def make_object_list(
        self,
        *,
        job_metadata: JobMetadata,
        cogt_run_params: CogtRunParams,
        object_class: type[BaseModelTypeVar],
        llm_setting_for_object_list: LLMSetting,
        unrendered_prompt: UnrenderedLLMPrompt,
        nb_items: int | None = None,
    ) -> LLMObjectListGeneration[BaseModelTypeVar]:
        self._record(entry_point="make_object_list", unrendered_prompt=unrendered_prompt)
        return await super().make_object_list(
            job_metadata=job_metadata,
            cogt_run_params=cogt_run_params,
            object_class=object_class,
            llm_setting_for_object_list=llm_setting_for_object_list,
            unrendered_prompt=unrendered_prompt,
            nb_items=nb_items,
        )


@pytest.fixture
def stored_text_storage() -> InMemoryStorageProvider:
    """A storage holding the stored text under the run's read scope."""
    storage = InMemoryStorageProvider()
    storage.root[STORED_TEXT_KEY] = STORED_TEXT.encode("utf-8")
    return storage


@pytest.fixture
def recording_content_generator(stored_text_storage: InMemoryStorageProvider) -> Generator[RecordingContentGenerator, None, None]:
    """The run's content generator for the test: in-process, over the storage holding the stored text."""
    content_generator = RecordingContentGenerator(generated_content_factory=GeneratedContentFactory(storage_provider=stored_text_storage))
    with scoped_content_generator(content_generator):
        yield content_generator


@pytest.fixture
def scoped_job_metadata(request: pytest.FixtureRequest) -> JobMetadata:
    """A run with a read scope, so every load of the stored text is authorized against it."""
    test_id: str = request.node.nodeid  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    return JobMetadata(
        run_metadata=RunMetadata(storage_scope=STORAGE_SCOPE, read_scope=READ_SCOPE, user_id="pytest", pipeline_run_id=f"{test_id}-stored-prompt")
    )
