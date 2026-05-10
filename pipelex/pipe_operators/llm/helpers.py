from pipelex.cogt.templating.template_category import TemplateCategory
from pipelex.cogt.templating.template_rendering import render_template
from pipelex.config import get_config
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.hub import (
    get_class_registry,
    get_required_concept,
)
from pipelex.tools.typing.structure_printer import StructurePrinter


async def get_output_structure_prompt(concept_ref: str) -> str | None:
    concept = get_required_concept(concept_ref=concept_ref)
    output_class = get_class_registry().get_class(concept.structure_class_name)
    if not output_class:
        return None

    class_structure = StructurePrinter().get_type_structure(tp=output_class, base_class=StuffContent)

    if not class_structure:
        return None
    class_structure_str = "\n".join(class_structure)
    llm_config = get_config().cogt.llm_config
    template_source = llm_config.get_template(template_name="output_structure_prompt")

    return await render_template(
        template=template_source,
        category=TemplateCategory.LLM_PROMPT,
        context={
            "class_structure_str": class_structure_str,
        },
    )
