"""Unit tests for PipelexBundleSpec.rendered_pretty rich rendering."""

from rich.console import Console

from pipelex.builder.bundle_spec import PipelexBundleSpec
from pipelex.builder.concept.concept_spec import ConceptSpec
from pipelex.builder.pipe.pipe_llm_spec import PipeLLMSpec
from pipelex.builder.pipe.pipe_sequence_spec import PipeSequenceSpec
from pipelex.builder.pipe.sub_pipe_spec import SubPipeSpec


def make_llm_spec(pipe_code: str) -> PipeLLMSpec:
    return PipeLLMSpec(
        pipe_code=pipe_code,
        description=f"Generate text for {pipe_code}",
        inputs={"topic": "Text"},
        output="Text",
        prompt="Write about $topic",
        model="$writing-creative",
    )


def make_full_bundle_spec() -> PipelexBundleSpec:
    return PipelexBundleSpec(
        domain="test_domain",
        description="A bundle that writes articles",
        system_prompt="You are a concise writer",
        main_pipe="main_seq",
        concept={
            "Article": ConceptSpec(concept_code="Article", description="A written article", refines="Text"),
            "Summary": "A short summary of a document",
        },
        pipe={
            "main_seq": PipeSequenceSpec(
                pipe_code="main_seq",
                description="Sequence main_seq",
                inputs={"topic": "Text"},
                output="Text",
                steps=[SubPipeSpec(pipe_code="step_one", result="step_one_result")],
            ),
            "step_one": make_llm_spec("step_one"),
        },
    )


def render_to_text(bundle_spec: PipelexBundleSpec, title: str | None = None) -> str:
    console = Console(record=True, color_system=None, width=300)
    console.print(bundle_spec.rendered_pretty(title=title))
    return console.export_text()


class TestPipelexBundleSpecRenderedPretty:
    def test_full_render_with_title(self) -> None:
        """A full bundle renders title, header info, system prompt and both tables."""
        rendered = render_to_text(make_full_bundle_spec(), title="Bundle Overview")

        assert "Bundle Overview" in rendered
        assert "Domain: test_domain" in rendered
        assert "Description: A bundle that writes articles" in rendered
        assert "Main Pipe: main_seq" in rendered
        assert "System Prompt: You are a concise writer" in rendered

    def test_concepts_table_renders_spec_and_string_rows(self) -> None:
        """The Concepts table shows a full ConceptSpec row and a string-reference row."""
        rendered = render_to_text(make_full_bundle_spec())

        assert "Concepts" in rendered
        assert "Concept: Article" in rendered
        assert "Refines: Text" in rendered
        assert "Description: A written article" in rendered
        assert "Summary: A short summary of a document" in rendered

    def test_pipes_table_lists_each_pipe(self) -> None:
        """The Pipes table lists every pipe with its type, inputs and output concept codes."""
        rendered = render_to_text(make_full_bundle_spec())

        assert "Pipes" in rendered
        assert "Pipe: main_seq" in rendered
        assert "Type: PipeSequence (PipeController)" in rendered
        assert "Sequence Steps:" in rendered
        assert "Pipe: step_one" in rendered
        assert "Type: PipeLLM (PipeOperator)" in rendered
        assert "Input: topic (Text)" in rendered
        assert "Output: Text" in rendered

    def test_minimal_render_omits_optional_sections(self) -> None:
        """Without title, description and system_prompt, those sections are absent from the output."""
        bundle_spec = PipelexBundleSpec(
            domain="test_domain",
            main_pipe="step_one",
            pipe={"step_one": make_llm_spec("step_one")},
        )

        rendered = render_to_text(bundle_spec)

        assert "Domain: test_domain" in rendered
        assert "Main Pipe: step_one" in rendered
        assert "Description: A bundle" not in rendered
        assert "System Prompt:" not in rendered
        assert "Concepts" not in rendered
        assert "Pipes" in rendered
