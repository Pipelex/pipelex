from kajson import kajson

from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.composite_content import CompositeContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.runtime_bridge.primitives.hydration import hydrate_working_memory


class TestCompositeContent:
    def test_named_sub_contents_are_top_level_fields(self):
        """Branch names must surface as top-level serialized fields, with no wrapper key."""
        composite = CompositeContent.model_validate(
            {
                "short_summary": TextContent(text="short"),
                "detailed_summary": TextContent(text="long and detailed"),
            }
        )
        dump = composite.smart_dump()
        assert set(dump.keys()) == {"short_summary", "detailed_summary"}
        assert dump["short_summary"]["text"] == "short"
        assert dump["detailed_summary"]["text"] == "long and detailed"

    def test_model_validate_preserves_unknown_fields(self):
        """The whole point of Composite: unknown fields must NOT be silently dropped."""
        composite = CompositeContent.model_validate({"alpha": {"text": "a"}, "beta": {"text": "b"}})
        dump = composite.smart_dump()
        assert set(dump.keys()) == {"alpha", "beta"}

    def test_kajson_round_trip(self):
        composite = CompositeContent.model_validate(
            {
                "tone_result": TextContent(text="cheerful"),
                "length_result": TextContent(text="short"),
            }
        )
        serialized = kajson.dumps(composite)
        rehydrated = kajson.loads(serialized)
        assert isinstance(rehydrated, CompositeContent)
        assert rehydrated.smart_dump() == composite.smart_dump()

    def test_transport_dump_and_hydrate_round_trip(self):
        """dump_for_transport → hydrate_working_memory must rebuild a CompositeContent main stuff."""
        composite = CompositeContent.model_validate(
            {
                "tone_result": TextContent(text="cheerful"),
                "length_result": TextContent(text="short"),
            }
        )
        concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.COMPOSITE)
        stuff = StuffFactory.make_stuff(concept=concept, content=composite, name="combo")
        working_memory = WorkingMemoryFactory.make_from_single_stuff(stuff)

        raw = working_memory.dump_for_transport()
        hydrated_memory = hydrate_working_memory(raw)

        hydrated_stuff = hydrated_memory.get_stuff("combo")
        assert isinstance(hydrated_stuff.content, CompositeContent)
        assert hydrated_stuff.content.smart_dump() == composite.smart_dump()

    def test_rendered_markdown_surfaces_named_sub_contents(self):
        composite = CompositeContent.model_validate(
            {
                "tone_result": TextContent(text="cheerful tone"),
                "length_result": TextContent(text="rather short"),
            }
        )
        markdown = composite.rendered_markdown()
        assert "tone_result" in markdown
        assert "cheerful tone" in markdown
        assert "length_result" in markdown
        assert "rather short" in markdown

    def test_rendered_html_surfaces_named_sub_contents(self):
        composite = CompositeContent.model_validate(
            {
                "tone_result": TextContent(text="cheerful tone"),
                "length_result": TextContent(text="rather short"),
            }
        )
        html = composite.rendered_html()
        assert "tone_result" in html
        assert "cheerful tone" in html
        assert "length_result" in html
        assert "rather short" in html
