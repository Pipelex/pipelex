from pathlib import Path

import pytest

from pipelex.pipeline.validate_in_process import validate_bundles_in_process

_SOURCE_GRAPH_DOMAIN = "validate_graph_registry_sources"
_SOURCE_GRAPH_MTHDS = f"""
domain = "{_SOURCE_GRAPH_DOMAIN}"
description = "Bundle for graph registry source path tests"
main_pipe = "echo_topic"

[concept.Topic]
description = "A generated topic"

[concept.Topic.structure]
name = {{ type = "text", description = "Topic name" }}

[pipe.echo_topic]
type = "PipeLLM"
description = "Pipe used to verify graph registry source paths"
inputs = {{ subject = "Text" }}
output = "Topic"
prompt = "Echo the $subject as a topic"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestValidateGraphRegistrySources:
    async def test_registry_entries_include_source_from_mthds_sources(self, tmp_path: Path) -> None:
        """A validation graph carries declaration sources from the loaded bundle source map."""
        bundle_path = tmp_path / "source_graph.mthds"
        bundle_path.write_text(_SOURCE_GRAPH_MTHDS, encoding="utf-8")
        source = str(bundle_path)

        report = await validate_bundles_in_process(
            mthds_contents=[bundle_path.read_text(encoding="utf-8")],
            mthds_sources=[source],
            library_dirs=[],
            log_context="test_validate_graph_registry_sources",
        )

        assert report.graph_spec is not None
        assert report.graph_spec.pipe_registry[f"{_SOURCE_GRAPH_DOMAIN}.echo_topic"]["source"] == source
        assert report.graph_spec.concept_registry[f"{_SOURCE_GRAPH_DOMAIN}.Topic"]["source"] == source
        assert report.graph_spec.concept_registry[f"{_SOURCE_GRAPH_DOMAIN}.Topic"]["json_schema"]
