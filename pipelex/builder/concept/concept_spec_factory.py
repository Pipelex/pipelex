from pipelex.builder.concept.concept_spec import ConceptSpec, ConceptSpecDraft, ConceptStructureSpec
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def create_concept_spec(working_memory: WorkingMemory) -> ConceptSpec:
    concept_spec_draft = working_memory.get_stuff_as(name="concept_spec_draft", content_type=ConceptSpecDraft)
    concept_spec_structures_stuff = working_memory.get_stuff_as_list(name="concept_spec_structures", item_type=ConceptStructureSpec)

    structure_dict: dict[str, ConceptStructureSpec] = {}
    for structure_item in concept_spec_structures_stuff.items:
        structure_spec = ConceptStructureSpec(
            the_field_name=structure_item.the_field_name,
            description=structure_item.description,
            type=structure_item.type,
            required=structure_item.required,
            default_value=structure_item.default_value,
        )
        structure_dict[structure_item.the_field_name] = structure_spec

    return ConceptSpec(
        the_concept_code=concept_spec_draft.the_concept_code,
        description=concept_spec_draft.description,
        structure=structure_dict,
        refines=concept_spec_draft.refines,
    )
