from pathlib import Path
from typing import Any

import pytest

from pipelex.config import get_config
from pipelex.core.stuffs.image_content import ImageContent
from pipelex.graph.graphspec import GraphSpec, NodeSpec
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode

_DOMAIN = "run_view_meaning"
_BUNDLE = f"""
domain = "{_DOMAIN}"
description = "Review a request and say what was decided"
main_pipe = "review"

[concept.Review]
description = "A review of a request"

[concept.Review.structure.verdict]
type = "text"
description = "What the review decided"
required = true
choices = [{{ value = "approve", label = "Approved", tone = "positive" }}, "reject"]
hints = {{ part = "verdict" }}

[concept.Review.structure.note]
type = "text"
description = "A note"
required = true

[pipe.review]
type = "PipeSequence"
description = "Route the request, then conclude"
activity = "Reviewing the request"
inputs = {{ request = "Text" }}
output = "Review"
steps = [
  {{ pipe = "route", result = "routed" }},
  {{ pipe = "conclude", result = "review" }},
]

[pipe.route]
type = "PipeCondition"
description = "Escalate an urgent request, file any other"
inputs = {{ request = "Text" }}
output = "Text"
expression = "request"
outcomes = {{ urgent = {{ pipe = "escalate", label = "Escalated", tone = "caution" }} }}
default_outcome = {{ pipe = "file_away", label = "Filed" }}

[pipe.escalate]
type = "PipeCompose"
description = "Escalate the request"
activity = "Escalating the request"
inputs = {{ request = "Text" }}
output = "Text"
template = "Escalated: $request"

[pipe.file_away]
type = "PipeCompose"
description = "File the request"
inputs = {{ request = "Text" }}
output = "Text"
template = "Filed: $request"

[pipe.conclude]
type = "PipeCompose"
description = "Conclude"
inputs = {{ routed = "Text" }}
output = "Review"

[pipe.conclude.construct]
verdict = "approve"
note = {{ from = "routed" }}
"""

_MANIFEST = f"""
[package]
address = "github.com/pipelex-tests/run-view-meaning"
version = "1.0.0"
description = "A method wording its result line"
main_pipe = "review"
result_line = "{{{{ output.verdict | upper }}}}: {{{{ output.note }}}}"

[exports.{_DOMAIN}]
pipes = ["review"]
"""

_IMAGES_BUNDLE = """
domain = "run_view_naming"
description = "Draw covers named after their client"
main_pipe = "draw"

[pipe.draw]
type = "PipeImgGen"
description = "Draw the covers"
inputs = { client = "Text" }
output = "Image[2]"
prompt = "A cover for $client"
output_filename = "{{ client }} cover"
"""


def _nodes_by_code(graph_spec: GraphSpec) -> dict[str, NodeSpec]:
    return {node.pipe_code: node for node in graph_spec.nodes if node.pipe_code}


def _live_runner(**kwargs: Any) -> PipelexMTHDSProtocol:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
    return PipelexMTHDSProtocol(execution_config=execution_config, **kwargs)


@pytest.mark.asyncio(loop_scope="class")
class TestRunViewMeaning:
    @pytest.mark.parametrize(
        ("request_text", "chosen_pipe", "label", "tone"),
        [("urgent", "escalate", "Escalated", "caution"), ("routine", "file_away", "Filed", None)],
        ids=["matched_outcome", "default_outcome"],
    )
    async def test_the_graph_carries_activities_and_the_label_of_the_outcome_taken(
        self, request_text: str, chosen_pipe: str, label: str, tone: str | None
    ) -> None:
        """A node shows its pipe's activity beside its description, and the condition's node names the outcome by its label."""
        response = await _live_runner().execute(mthds_contents=[_BUNDLE], inputs={"request": request_text})

        graph_spec = response.pipe_output.graph_spec
        assert graph_spec is not None
        nodes = _nodes_by_code(graph_spec)
        assert nodes["review"].activity == "Reviewing the request"
        assert nodes["review"].description == "Route the request, then conclude"
        assert nodes["conclude"].activity is None
        if chosen_pipe == "escalate":
            assert nodes["escalate"].activity == "Escalating the request"
        resolution = nodes["route"].execution_data
        assert resolution["selected_outcome"] == f"{_DOMAIN}.{chosen_pipe}"
        assert resolution["selected_outcome_label"] == label
        assert resolution.get("selected_outcome_tone") == tone

    async def test_a_run_derives_its_result_line_from_the_verdict_field(self) -> None:
        """With no manifest, the line is the label of the verdict the output holds."""
        response = await _live_runner().execute(mthds_contents=[_BUNDLE], inputs={"request": "routine"})

        assert response.pipe_output.result_line == "Approved"

    async def test_a_run_renders_the_result_line_its_manifest_writes(self, tmp_path: Path) -> None:
        """The manifest's template is rendered against the main pipe's output, as the wire carries it."""
        method_dir = tmp_path / "method"
        method_dir.mkdir()
        (method_dir / "METHODS.toml").write_text(_MANIFEST, encoding="utf-8")
        (method_dir / "review.mthds").write_text(_BUNDLE, encoding="utf-8")

        response = await _live_runner(library_dirs=[str(method_dir)]).execute(pipe_code=f"{_DOMAIN}.review", inputs={"request": "urgent"})

        assert response.pipe_output.result_line == "APPROVE: Escalated: urgent"

    async def test_produced_files_take_the_name_output_filename_builds(self) -> None:
        """The name is rendered once with the inputs, made safe, given each file's extension, and numbered after the first."""
        runner = PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.DRY, is_mock_usage=True)
        response = await runner.execute(mthds_contents=[_IMAGES_BUNDLE], inputs={"client": "Acme/Corp"})

        images = response.pipe_output.main_stuff_as_items(item_type=ImageContent)
        assert len(images) == 2
        extensions = [Path(image.url).suffix for image in images]
        assert [image.filename for image in images] == [f"Acme-Corp cover{extensions[0]}", f"Acme-Corp cover (2){extensions[1]}"]
