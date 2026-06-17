from typing import Any

from typing_extensions import override

from pipelex.cogt.templating.template_blueprint import TemplateBlueprint
from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.pipes.pipe_factory import PipeFactoryProtocol
from pipelex.core.pipes.stuff_spec.stuff_spec import StuffSpec
from pipelex.hub import get_concept_library, get_native_concept
from pipelex.pipe_operators.search.pipe_search import PipeSearch
from pipelex.pipe_operators.search.pipe_search_blueprint import PipeSearchBlueprint


class PipeSearchFactory(PipeFactoryProtocol[PipeSearchBlueprint, PipeSearch]):
    @classmethod
    @override
    def make(
        cls,
        pipe_category: Any,
        *,
        pipe_type: str,
        pipe_code: str,
        domain_code: str,
        description: str,
        inputs: InputStuffSpecs,
        output: StuffSpec,
        blueprint: PipeSearchBlueprint,
    ) -> PipeSearch:
        concept_library = get_concept_library()

        prompt_blueprint = TemplateBlueprint(
            template=blueprint.prompt,
            category=TemplateCategory.BASIC,
        )

        # Determine if output is structured (not SearchResult)
        search_result_concept = get_native_concept(native_concept=NativeConceptCode.SEARCH_RESULT)
        is_structured_output = not concept_library.is_compatible(
            tested_concept=output.concept,
            wanted_concept=search_result_concept,
            strict=True,
        )

        return PipeSearch(
            domain_code=domain_code,
            code=pipe_code,
            description=description,
            output=output,
            inputs=inputs,
            search_choice=blueprint.model,
            prompt_blueprint=prompt_blueprint,
            include_images_override=blueprint.include_images,
            max_results_override=blueprint.max_results,
            from_date=blueprint.from_date,
            to_date=blueprint.to_date,
            include_domains=blueprint.include_domains,
            exclude_domains=blueprint.exclude_domains,
            is_structured_output=is_structured_output,
        )
