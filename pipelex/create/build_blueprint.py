from __future__ import annotations

from typing import Optional, cast

from pipelex import pretty_print
from pipelex.core.stuffs.stuff_content import ListContent
from pipelex.create.helpers import get_support_file
from pipelex.libraries.pipelines.builder.builder import PipelexBundleBlueprint
from pipelex.libraries.pipelines.builder.concept.concept import ConceptBlueprint
from pipelex.libraries.pipelines.builder.pipe.pipe import PipeBlueprintUnion
from pipelex.pipeline.execute import execute_pipeline


async def do_build_blueprint(
    brief: str,
    output_path: Optional[str],
) -> None:
    pipe_output = await execute_pipeline(
        pipe_code="build_drafts_from_brief",
        input_memory={
            "brief": brief,
            "concept_rules": get_support_file(subpath="create/structures.md"),
        },
    )
    pretty_print(pipe_output, title="Pipe Output")
    concepts = pipe_output.working_memory.get_stuff_as_list(name="concept_blueprints", item_type=ConceptBlueprint)
    pipes = cast(ListContent[PipeBlueprintUnion], pipe_output.main_stuff)
    blueprint = PipelexBundleBlueprint(
        domain="test", concept={concept.the_concept_code: concept for concept in concepts.items}, pipe={pipe.pipe_code: pipe for pipe in pipes.items}
    )
    pretty_print(blueprint, title="Pipelex Bundle Blueprint")
