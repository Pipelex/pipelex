import pytest

from pipelex import pretty_print
from pipelex.core.pipe.pipe_run_params import PipeRunMode
from pipelex.create.helpers import get_support_file
from pipelex.libraries.pipelines.meta.pipeline_draft import PipelexBundleBlueprint
from pipelex.pipeline.execute import execute_pipeline


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.dry_runnable
@pytest.mark.llm
@pytest.mark.inference
@pytest.mark.parametrize(
    "requirements",
    [
        (
            "Create a domain 'sample' to describe simple demo pipelines. "
            "Define concept ThingDescription = 'A short natural language description of a thing'. "
            "Add a pipe write_thing that takes input { text = Text } and outputs ThingDescription using PipeLLM."
        ),
        (
            "Domain: gadgets. Concept: GadgetSpec = 'Technical description of a gadget'. "
            "Add pipe summarize_gadget: inputs { text = Text } -> output GadgetSpec via PipeLLM."
        ),
    ],
)
async def test_generate_pipeline_blueprint(pipe_run_mode: PipeRunMode, requirements: str):
    pipe_output = await execute_pipeline(
        pipe_code="build_blueprint",
        input_memory={
            "domain": "test_domain",
            "pipeline_name": "test_pipeline",
            "requirements": requirements,
            "draft_pipeline_rules": get_support_file(subpath="create/draft_pipelines.md"),
            "build_pipeline_rules": get_support_file(subpath="create/build_pipelines.md"),
            "create_structured_output_rules": get_support_file(subpath="create/structures.md"),
        },
        pipe_run_mode=pipe_run_mode,
    )

    blueprint = pipe_output.main_stuff_as(content_type=PipelexBundleBlueprint)
    assert isinstance(blueprint, PipelexBundleBlueprint)
    # Basic sanity checks
    assert isinstance(blueprint.domain, str) and blueprint.domain != ""

    pretty_print(blueprint, title="PipelexBundleBlueprint")
