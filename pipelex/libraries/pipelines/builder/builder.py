from typing import Dict, cast

from pydantic import Field

from pipelex import pretty_print
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint as PipelexBundleBlueprintBaseModel
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.stuff_content import ListContent, StructuredContent
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint as ConceptBlueprintBaseModel
from pipelex.libraries.pipelines.builder.concept.concept import ConceptBlueprint, ConceptSpec
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprintUnion, PipeSignature


class PipelexBundleBlueprintDraft(StructuredContent):
    """Complete blueprint of a pipeline library TOML file."""

    domain: str = Field(description="The domain of the pipeline library.")
    definition: str = Field(description="The definition of the pipeline library.")

    concept: Dict[str, ConceptSpec] = Field(default_factory=dict, description="The concepts of the pipeline library.")

    pipe: Dict[str, PipeSignature] = Field(default_factory=dict, description="The pipes of the pipeline library.")


class PipelexBundleBlueprint(PipelexBundleBlueprintBaseModel, StructuredContent):
    """Complete blueprint of a pipeline library TOML file."""

    pass


def compile_in_pipelex_bundle_blueprint(working_memory: WorkingMemory) -> PipelexBundleBlueprint:
    """Construct a PipelexBundleBlueprint from working memory containing concept and pipe blueprints.
    
    Args:
        working_memory: WorkingMemory containing concept_blueprints and pipe_blueprints stuffs.
        
    Returns:
        PipelexBundleBlueprint: The constructed pipeline blueprint.
    """
    concept_blueprints = working_memory.get_stuff_as_list(
        name="concept_blueprints",
        item_type=ConceptBlueprint,
    )
    
    # Get pipe blueprints as ListContent directly and cast for typing
    # We can't use get_stuff_as_list with Union types, so we get the raw content
    pipe_blueprints = cast(
        ListContent[PipeBlueprintUnion],
        working_memory.get_stuff(name="pipe_blueprints").content_as(content_type=ListContent),
    )

    pretty_print(concept_blueprints, title="Concept Blueprints in PipeFunc")
    pretty_print(pipe_blueprints, title="Pipe Blueprints in PipeFunc")
    
    return PipelexBundleBlueprint(
        domain="builder",
        definition="Builder pipeline library",
        concept={concept.the_concept_code: ConceptBlueprintBaseModel(**concept.model_dump(exclude={"the_concept_code"})) for concept in concept_blueprints.items},
        pipe={pipe.pipe_code: pipe for pipe in pipe_blueprints.items},
    )
