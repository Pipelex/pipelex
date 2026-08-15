from typing import TYPE_CHECKING, Any, Literal

from typing_extensions import override

from pipelex import log
from pipelex.cogt.exceptions import ModelChoiceNotFoundError
from pipelex.cogt.models.model_deck_check import check_search_choice_with_deck
from pipelex.cogt.search.search_setting import SearchModelChoice
from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_output import PipeOutput
from pipelex.interpreter_hub import get_concept_library
from pipelex.kernel.search_ops import resolve_search_setting, run_search
from pipelex.kernel.templating_style_ops import resolve_templating_style
from pipelex.pipe_machinery.template_guard_lint import lint_optional_input_guards
from pipelex.pipe_operators.pipe_operator import PipeOperator
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata
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
    def needed_inputs(self, *, visited_pipes: set[str] | None = None) -> InputStuffSpecs:
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

        # Guard-lint (D7): every reference to a declared-optional input must be guarded.
        lint_optional_input_guards(
            pipe_code=self.code,
            domain_code=self.domain_code,
            inputs=self.inputs,
            template_source=self.prompt_blueprint.template,
            template_category=self.prompt_blueprint.category,
            template_label="prompt",
        )

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
        *,
        job_metadata: JobMetadata,
        working_memory: WorkingMemory,
        pipe_run_params: PipeRunParams,
        output_name: str | None = None,
    ) -> PipeSearchOutput:
        search_choice_desc = self.search_choice or "default"
        log.dev(f"✨ PipeSearch '{self.code}' running with search choice '{search_choice_desc}' ✨")

        # The deck chain, the handle resolution and the override application are kernel semantics; the
        # setting is resolved per run into a local and never cached onto `self`, for the reason
        # `pipe_llm.py` states about its own settings.
        search_setting = resolve_search_setting(
            search_choice=self.search_choice,
            include_images_override=self.include_images_override,
            max_results_override=self.max_results_override,
        )

        # The sourced-answer / structured fork stays here: it is declared on the pipe, and resolving the
        # output concept to a structure class is what a loaded library is for. Handing the class over
        # is what spares the kernel a library read.
        output_structure_class: type[StuffContent] | None = None
        if self.is_structured_output:
            output_structure_class = get_concept_library().get_structure_class(concept=self.output.concept)

        search_result = await run_search(
            memory=working_memory,
            template=self.prompt_blueprint.template,
            category=self.prompt_blueprint.category,
            search_setting=search_setting,
            concept=self.output.concept,
            job_metadata=job_metadata,
            cogt_run_params=pipe_run_params.cogt_run_params,
            # No authored style on this operator: a query template takes the runtime default, the
            # same one an LLM pipe that declares nothing gets.
            templating_style=resolve_templating_style(authored=None),
            output_structure_class=output_structure_class,
            include_domains=self.include_domains,
            exclude_domains=self.exclude_domains,
            from_date=self.from_date,
            to_date=self.to_date,
            result_name=output_name,
        )
        working_memory = search_result.memory

        # Capture execution data for the graph tracer
        execution_data_dict: dict[str, Any] = {
            "rendered_query": search_result.rendered_query,
            "resolved_model": search_result.search_setting.model,
            "is_structured_output": self.is_structured_output,
        }

        self._register_execution_data(job_metadata=job_metadata, execution_data=execution_data_dict)
        return PipeSearchOutput(
            working_memory=working_memory,
            pipeline_run_id=job_metadata.pipeline_run_id,
        )

    @override
    async def _validate_before_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass

    @override
    async def _validate_after_run(
        self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, pipe_run_params: PipeRunParams, output_name: str | None = None
    ):
        pass
