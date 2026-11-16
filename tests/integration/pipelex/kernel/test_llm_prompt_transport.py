"""An LLM prompt and its generation across a host runtime's activity boundary: encoded on one side, decoded where the run's library is not held.

A host runtime carries the prompt into the leaf, and the generation back, through kajson, as the Temporal data converter
does. The far side of each test decodes with no library current and the run's library torn down, so a class the run's
bundle built exists nowhere it could be found by name.
"""

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

import pytest
from kajson import kajson

from pipelex.cogt.content_generation.object_revalidation import revalidate_object_generation, revalidate_object_list_generation
from pipelex.cogt.llm.llm_generation import GeneratedObjectData, LLMObjectGeneration, LLMObjectListGeneration
from pipelex.cogt.llm.llm_prompt_trace import LLMPromptTrace
from pipelex.cogt.llm.unrendered_llm_prompt import UnrenderedLLMPrompt
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.interpreter_hub import get_concept_library, get_current_library_id_or_none, get_library_manager, scoped_current_library
from pipelex.kernel.llm_prompt_content import LlmPromptContent, prepare_llm_prompt, render_llm_prompt
from pipelex.libraries.concepts_libraries import CONCEPTS_LIBRARIES
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.runtime_hub import get_class_registry
from pipelex.tools.storage.in_memory_storage_provider import InMemoryStorageProvider
from pipelex.tools.templating.templating_style import TagStyle, TemplatingStyle
from pipelex.tools.templating.text_format import TextFormat

_STYLE = TemplatingStyle(tag_style=TagStyle.NO_TAG, text_format=TextFormat.PLAIN)

_BUNDLE_MTHDS = """
domain = "prompt_transport_tests"
description = "Reading invoices"

[concept.TransportedInvoice]
description = "An invoice"

[concept.TransportedInvoice.structure]
number = { type = "text", description = "The invoice number", required = true }
total  = { type = "number", description = "The total, in euros", required = true }
"""

_INVOICE_CLASS_NAME = "TransportedInvoice"
_INVOICE_INPUTS: dict[str, Any] = {
    "invoice": {"concept": "prompt_transport_tests.TransportedInvoice", "content": {"number": "INV-2026-0207", "total": 12.5}},
}

_READ_SCOPE = "org_abc"
_STORED_KEY = "org_abc/mt_1/run_9/generated/89abcdef/note.txt"
_STORED_TEXT = "A note long enough to have been stored, which only the leaf reads.\n" * 4


class _RunSide:
    """What the run's side of the boundary built, in its library, before the library was torn down."""

    def __init__(self) -> None:
        self.encoded: str = ""
        self.invoice_class: type[Any] | None = None
        self.invoice: Any = None


@contextmanager
def _run_library() -> Generator[WorkingMemory, None, None]:
    """The run's library, holding the bundle, current for the block and torn down after it, with the run's memory."""
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    try:
        with scoped_current_library(library_id=library_id):
            library_manager.load_from_blueprints(
                library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_BUNDLE_MTHDS)]
            )
            yield WorkingMemoryFactory.make_from_pipeline_inputs(_INVOICE_INPUTS, concept_provider=get_concept_library(), read_scope=None)
    finally:
        library_manager.teardown(library_id=library_id)


def _assert_far_side() -> None:
    """The far side holds no library, and no class the run's bundle built."""
    assert get_current_library_id_or_none() is None
    assert get_class_registry().get_class(name=_INVOICE_CLASS_NAME) is None


@pytest.fixture
def released_concepts_libraries() -> Generator[None, None, None]:
    yield
    CONCEPTS_LIBRARIES.release_idle()


@pytest.mark.asyncio(loop_scope="class")
class TestLLMPromptTransport:
    @pytest.mark.usefixtures("released_concepts_libraries")
    async def test_a_prompt_reading_a_bundle_concept_renders_where_the_run_s_library_is_not_held(self) -> None:
        run_side = _RunSide()
        with _run_library() as memory:
            prompt_content = LlmPromptContent.make_from_text(user="Invoice {{ invoice.number }} totals {{ invoice.total }} euros.")
            unrendered_prompt = prepare_llm_prompt(prompt_content=prompt_content, memory=memory, templating_style=_STYLE)
            assert unrendered_prompt.context.concepts_crate is not None
            assert "prompt_transport_tests.TransportedInvoice" in unrendered_prompt.context.concepts_crate["concepts"]
            assert unrendered_prompt.context.concepts_crate["pipes"] == {}
            run_side.encoded = kajson.dumps(unrendered_prompt)

        _assert_far_side()
        decoded = kajson.loads(run_side.encoded)
        assert isinstance(decoded, UnrenderedLLMPrompt)
        assert decoded.context.in_process_memory is None

        rendered_prompt = await render_llm_prompt(unrendered_prompt=decoded, read_scope=None, storage_provider=None)

        assert rendered_prompt.user_text == "Invoice INV-2026-0207 totals 12.5 euros."
        assert len(CONCEPTS_LIBRARIES.held_library_ids()) == 1
        _assert_far_side()

    async def test_a_prompt_reading_a_native_stored_text_renders_with_no_library_and_crosses_as_its_reference(self) -> None:
        text_concept = ConceptFactory.make_native_concept(native_concept_code=NativeConceptCode.TEXT)
        stored_note = TextContent.model_validate(
            {
                "url": f"pipelex-storage://{_STORED_KEY}",
                "size": len(_STORED_TEXT.encode("utf-8")),
                "mime_type": "text/plain",
                "preview": _STORED_TEXT[:40],
            }
        )
        memory = WorkingMemoryFactory.make_from_single_stuff(stuff=StuffFactory.make_stuff(concept=text_concept, content=stored_note, name="note"))
        unrendered_prompt = prepare_llm_prompt(
            prompt_content=LlmPromptContent.make_from_text(user="Read this note:\n{{ note.text }}"), memory=memory, templating_style=_STYLE
        )
        # A memory of native stuffs needs no concepts to be typed again.
        assert unrendered_prompt.context.concepts_crate is None
        encoded = kajson.dumps(unrendered_prompt)
        assert _STORED_TEXT not in encoded

        decoded = kajson.loads(encoded)
        assert isinstance(decoded, UnrenderedLLMPrompt)
        assert decoded.context.in_process_memory is None
        storage = InMemoryStorageProvider()
        storage.root[_STORED_KEY] = _STORED_TEXT.encode("utf-8")
        rendered_prompt = await render_llm_prompt(unrendered_prompt=decoded, read_scope=_READ_SCOPE, storage_provider=storage)

        assert rendered_prompt.user_text == f"Read this note:\n{_STORED_TEXT}"

    async def test_an_object_generation_of_a_bundle_concept_decodes_as_data_and_revalidates_into_the_caller_s_class(self) -> None:
        run_side = _RunSide()
        trace = LLMPromptTrace(user_text="Extract the invoice.")
        with _run_library() as memory:
            invoice = memory.get_stuff(name="invoice").content
            run_side.invoice_class = type(invoice)
            run_side.invoice = invoice
            run_side.encoded = kajson.dumps(LLMObjectGeneration(generated_object=invoice, rendered_prompt=trace))
            encoded_list = kajson.dumps(LLMObjectListGeneration(generated_objects=[invoice, invoice], rendered_prompt=trace))

        _assert_far_side()
        decoded_value = kajson.loads(run_side.encoded)
        decoded_list_value = kajson.loads(encoded_list)
        assert isinstance(decoded_value, LLMObjectGeneration)
        assert isinstance(decoded_list_value, LLMObjectListGeneration)
        decoded = cast("LLMObjectGeneration[Any]", decoded_value)
        decoded_list = cast("LLMObjectListGeneration[Any]", decoded_list_value)
        assert isinstance(decoded.generated_object, GeneratedObjectData)
        assert decoded.generated_object.model_dump() == {"number": "INV-2026-0207", "total": 12.5}
        assert decoded.rendered_prompt == trace

        # The caller holds the output's class, as the workflow does, and validates the data into it.
        assert run_side.invoice_class is not None
        revalidated = revalidate_object_generation(generation=decoded, object_class=run_side.invoice_class, is_mock_built=False, dump_mode="json")
        revalidated_list = revalidate_object_list_generation(
            generation=decoded_list, object_class=run_side.invoice_class, is_mock_built=False, dump_mode="json"
        )
        assert type(revalidated.generated_object) is run_side.invoice_class
        assert revalidated.generated_object == run_side.invoice
        assert [type(generated) for generated in revalidated_list.generated_objects] == [run_side.invoice_class, run_side.invoice_class]
        assert revalidated_list.rendered_prompt == trace

    async def test_an_object_generation_round_trips_through_plain_json_too(self) -> None:
        trace = LLMPromptTrace(user_text="Extract the invoice.")
        with _run_library() as memory:
            invoice = memory.get_stuff(name="invoice").content
            dumped = LLMObjectGeneration(generated_object=invoice, rendered_prompt=trace).model_dump_json()

        decoded = LLMObjectGeneration[Any].model_validate_json(dumped)

        assert isinstance(decoded.generated_object, GeneratedObjectData)
        assert decoded.generated_object.model_dump() == {"number": "INV-2026-0207", "total": 12.5}
