from typing import TYPE_CHECKING, Literal

from typing_extensions import override

from pipelex import log
from pipelex.cogt.content_generation.dry_run_factory import DryRunFactory
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.model_deck_check import check_search_choice_with_deck
from pipelex.cogt.search.search_job_factory import SearchJobFactory
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.cogt.search.search_worker_factory import SearchWorkerFactory
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.core.stuffs.search_result_content import SearchResultContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.hub import get_model_deck
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.pipeline.job_metadata import JobMetadata
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

if TYPE_CHECKING:
    from pipelex.core.stuffs.stuff_content import StuffContent


class PipeSearchOutput(PipeOutput):
    pass


class PipeSearch(PipeOperator[PipeSearchOutput]):
    type: Literal["PipeSearch"] = "PipeSearch"
    search_choice: SearchModelChoice | None
    prompt_blueprint: TemplateBlueprint
    include_images_override: bool | None = None
    max_results_override: int | None = None
    from_date: str | None = None
    to_date: str | None = None
    include_domains: list[str] | None = None
    exclude_domains: list[str] | None = None
    is_structured_output: bool

    @override
    def needed_inputs(self, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
        return self.inputs

    @override
    def required_variables(self) -> set[str]:
        full_paths = self.prompt_blueprint.required_variables()
        return {get_root_from_dotted_path(path) for path in full_paths if not path.startswith("_")}

    @override
    def validate_inputs_static(self):
        if self.search_choice:
            try:
                check_search_choice_with_deck(search_choice=self.search_choice)
            except ModelChoiceNotFoundError as exc:
                msg = f"Search choice '{self.search_choice}' was not found in the model deck"
                raise ValueError(msg) from exc

    @override
    def validate_inputs_with_library(self):
        pass

    @override
    def validate_output_static(self):
        pass

    @override
    def validate_output_with_library(self):
        pass

    @override
    async def _live_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeSearchOutput:
        # 0. Log the search run
        search_choice_desc = self.search_choice or "default"
        log.dev(f"✨ PipeSearch '{self.code}' running with search choice '{search_choice_desc}' ✨")

        # 1. Render the prompt template against working memory context
        query_text = await render_template(
            template=self.prompt_blueprint.template,
            category=self.prompt_blueprint.category,
            context=working_memory.generate_context(),
        )

        # 2. Resolve SearchSetting from deck
        model_deck = get_model_deck()
        search_choice: SearchModelChoice = self.search_choice or model_deck.search_choice_default
        search_setting: SearchSetting = model_deck.get_search_setting(search_choice=search_choice)

        # 3. Resolve the model handle (waterfalls/aliases → actual provider/variant handle)
        inference_model = model_deck.get_required_inference_model(model_handle=search_setting.model, model_type=ModelType.SEARCH)
        resolved_model_handle = inference_model.name
        if resolved_model_handle != search_setting.model:
            search_setting = search_setting.model_copy(update={"model": resolved_model_handle})

        # 4. Apply pipe-level overrides
        if self.include_images_override is not None:
            search_setting = search_setting.model_copy(update={"include_images": self.include_images_override})
        if self.max_results_override is not None:
            search_setting = search_setting.model_copy(update={"max_results": self.max_results_override})

        # 5. Get search worker from factory
        worker = SearchWorkerFactory.make_search_worker(inference_model=inference_model)

        # 6. Create search job
        search_job = SearchJobFactory.make_search_job(
            query=query_text,
            search_setting=search_setting,
            job_metadata=job_metadata,
            include_domains=self.include_domains,
            exclude_domains=self.exclude_domains,
            from_date=self.from_date,
            to_date=self.to_date,
        )

        # 7. Execute search based on output type
        content: StuffContent
        if not self.is_structured_output:
            content = await worker.search_sourced_answer(search_job=search_job)
        else:
            output_structure_class = self.output.concept.get_structure_class()
            result_dict = await worker.search_structured(search_job=search_job, schema=output_structure_class)
            content = output_structure_class.model_validate(result_dict)

        # 8. Create Stuff, set in working memory, and return output
        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
            content=content,
        )
        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )
        return PipeSearchOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _dry_run_operator_pipe(
        self,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeSearchOutput:
        content: StuffContent
        if not self.is_structured_output:
            doc_factory = DryRunFactory.make_dry_run_factory(DocumentContent)
            mock_sources = [doc_factory.build() for _ in range(3)]
            search_result_factory = DryRunFactory.make_dry_run_factory(SearchResultContent)
            content = search_result_factory.build(sources=mock_sources)
        else:
            output_structure_class = self.output.concept.get_structure_class()
            structured_factory = DryRunFactory.make_dry_run_factory(output_structure_class)
            content = structured_factory.build()

        output_stuff = StuffFactory.make_stuff(
            name=output_name,
            concept=self.output.concept,
            content=content,
        )
        working_memory.set_new_main_stuff(
            stuff=output_stuff,
            name=output_name,
        )
        return PipeSearchOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
