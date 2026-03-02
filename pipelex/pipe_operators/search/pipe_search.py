from typing import TYPE_CHECKING, Literal

from typing_extensions import override

from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_search_choice_with_deck
from pipelex.cogt.search.search_depth import SearchDepth
from pipelex.cogt.search.search_setting import SearchModelChoice, SearchSetting
from pipelex.cogt.search.search_worker_factory import get_search_worker
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
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
    depth_override: SearchDepth | None = None
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
        return {get_root_from_dotted_path(path) for path in full_paths}

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

        # 3. Apply pipe-level overrides
        if self.depth_override is not None:
            search_setting = search_setting.model_copy(update={"depth": self.depth_override})
        if self.include_images_override is not None:
            search_setting = search_setting.model_copy(update={"include_images": self.include_images_override})
        if self.max_results_override is not None:
            search_setting = search_setting.model_copy(update={"max_results": self.max_results_override})

        # 4. Get search worker from factory
        worker = get_search_worker(model_handle=search_setting.model)

        # 5/6. Execute search based on output type
        content: StuffContent
        if not self.is_structured_output:
            content = await worker.search_sourced_answer(
                query=query_text,
                search_setting=search_setting,
                include_domains=self.include_domains,
                exclude_domains=self.exclude_domains,
                from_date=self.from_date,
                to_date=self.to_date,
            )
        else:
            output_structure_class = self.output.concept.get_structure_class()
            result_dict = await worker.search_structured(
                query=query_text,
                search_setting=search_setting,
                output_schema=output_structure_class,
                include_domains=self.include_domains,
                exclude_domains=self.exclude_domains,
                from_date=self.from_date,
                to_date=self.to_date,
            )
            content = output_structure_class.model_validate(result_dict)

        # 7. Create Stuff, set in working memory, return output
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
        content = SearchResultContent(
            answer="[DRY RUN] Mock search result",
            sources=[],
        )

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
