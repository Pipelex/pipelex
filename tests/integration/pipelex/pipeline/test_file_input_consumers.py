"""The static walk that finds, for each input slot of an entry pipe, the operators that will consume its files.

It follows the slots by name through the controllers, the way the absence-taint analysis does: a
sequence visits its steps in order and stops following a slot a step overwrites, a batch maps the
list slot to its item slot, a parallel visits every branch, and a condition or a liftable step makes
whatever lies below it conditional. A `PipeFunc`, a `PipeCompose` or an unresolved pipe consumes
nothing as far as the walk knows. A `PipeExtract` consumes its document input with the formats its
resolved model reads, and a `PipeLLM` the documents its prompt references, by dotted path.
"""

from collections.abc import Callable

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.document_content import DocumentContent
from pipelex.interpreter_hub import get_library_manager, get_required_pipe
from pipelex.kernel.llm_ops import resolve_llm_setting_for_object, resolve_llm_setting_for_text
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline import file_input_consumers as file_input_consumers_module
from pipelex.pipeline.file_input_consumers import FileConsumerKind, FileInputConsumer, collect_file_input_consumers
from pipelex.runtime_hub import get_model_deck
from pipelex.system.registries.func_registry import func_registry

PDF_ONLY_MODEL = "pypdfium2-extract-pdf"
DOCLING_MODEL = "docling-extract-text"
DOCLING_FORMATS = frozenset({"pdf", "docx", "pptx", "xlsx", "html", "md", "csv", "txt", "vtt", "eml", "image"})

_EXTRACTORS_MTHDS = f"""
[pipe.extract_pdf]
type = "PipeExtract"
description = "Extract a transcript with a model reading PDF only"
inputs = {{ transcript = "Document" }}
output = "Page[]"
model = "{PDF_ONLY_MODEL}"

[pipe.extract_any]
type = "PipeExtract"
description = "Extract a transcript with a model reading Office files too"
inputs = {{ transcript = "Document" }}
output = "Page[]"
model = "{DOCLING_MODEL}"
"""


def file_consumers_replace_transcript(working_memory: WorkingMemory) -> DocumentContent:
    return DocumentContent(url=working_memory.get_stuff_as_document(name="transcript").url)


def _bundle(*, domain: str, pipes: str) -> str:
    return f'domain = "{domain}"\ndescription = "File input consumers test"\n{pipes}\n{_EXTRACTORS_MTHDS}'


def _consumers(*, load_empty_library: Callable[[], str], domain: str, pipes: str) -> dict[str, list[FileInputConsumer]]:
    """Load the bundle into a fresh library and walk its `main` pipe."""
    library_id = load_empty_library()
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=_bundle(domain=domain, pipes=pipes))
    get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    return collect_file_input_consumers(get_required_pipe(pipe_code=f"{domain}.main"))


def _summary(consumers: list[FileInputConsumer]) -> list[tuple[str, str, bool]]:
    return sorted((consumer.pipe_code, consumer.display_consumed_path, consumer.is_conditional) for consumer in consumers)


class TestFileInputConsumers:
    @pytest.fixture(autouse=True)
    def register_funcs(self):
        func_registry.register_function(file_consumers_replace_transcript)
        yield
        if func_registry.has_function(file_consumers_replace_transcript.__name__):
            func_registry.unregister_function_by_name(file_consumers_replace_transcript.__name__)

    def test_a_sequence_step_consumes_the_input(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Extract the transcript"
inputs = { transcript = "Document" }
output = "Page[]"
steps = [{ pipe = "extract_pdf", result = "pages" }]
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_seq", pipes=pipes)

        (consumer,) = consumers["transcript"]
        assert consumer.pipe_code == "extract_pdf"
        assert consumer.consumed_path == ("transcript",)
        assert consumer.model == PDF_ONLY_MODEL
        assert consumer.readable_formats == frozenset({"pdf"})
        assert consumer.reads_web_pages is False
        assert consumer.is_conditional is False

    def test_a_slot_overwritten_before_the_consumer_is_not_followed(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Replace the transcript, then extract it"
inputs = { transcript = "Document" }
output = "Page[]"
steps = [
    { pipe = "replace_transcript", result = "transcript" },
    { pipe = "extract_pdf", result = "pages" },
]

[pipe.replace_transcript]
type = "PipeFunc"
description = "Replace the transcript with another document"
inputs = { transcript = "Document" }
output = "Document"
function_name = "file_consumers_replace_transcript"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_overwrite", pipes=pipes)

        assert consumers.get("transcript", []) == []

    @pytest.mark.parametrize(
        ("domain", "main_inputs", "converter_pipe"),
        [
            (
                "fic_nested_overwrite",
                'transcript = "Document"',
                """
[pipe.convert_transcript]
type = "PipeSequence"
description = "Convert the transcript in place"
inputs = { transcript = "Document" }
output = "Document"
steps = [{ pipe = "replace_transcript", result = "transcript" }]
""",
            ),
            (
                "fic_condition_overwrite",
                'transcript = "Document", mode = "Text"',
                """
[pipe.convert_transcript]
type = "PipeCondition"
description = "Convert the transcript in place when asked to"
inputs = { transcript = "Document", mode = "Text" }
output = "Document"
expression = "mode"
default_outcome = "fail"

[pipe.convert_transcript.outcomes]
convert = "convert_in_place"

[pipe.convert_in_place]
type = "PipeSequence"
description = "Convert the transcript in place"
inputs = { transcript = "Document" }
output = "Document"
steps = [{ pipe = "replace_transcript", result = "transcript" }]
""",
            ),
        ],
    )
    def test_a_slot_a_nested_controller_overwrites_is_not_followed(
        self, load_empty_library: Callable[[], str], domain: str, main_inputs: str, converter_pipe: str
    ):
        """A nested sequence or a condition outcome runs on the caller's working memory, so what its steps write overwrites the caller's slots."""
        pipes = f"""
[pipe.main]
type = "PipeSequence"
description = "Convert the transcript, then extract it"
inputs = {{ {main_inputs} }}
output = "Page[]"
steps = [
    {{ pipe = "convert_transcript", result = "converted" }},
    {{ pipe = "extract_pdf", result = "pages" }},
]
{converter_pipe}
[pipe.replace_transcript]
type = "PipeFunc"
description = "Replace the transcript with another document"
inputs = {{ transcript = "Document" }}
output = "Document"
function_name = "file_consumers_replace_transcript"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain=domain, pipes=pipes)

        assert consumers.get("transcript", []) == []

    def test_a_batch_step_maps_the_list_slot_to_its_item_slot(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Extract every transcript"
inputs = { transcripts = "Document[]" }
output = "Page[]"
steps = [{ pipe = "extract_pdf", batch_over = "transcripts", batch_as = "transcript", result = "pages" }]
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_batch_step", pipes=pipes)

        assert _summary(consumers["transcripts"]) == [("extract_pdf", "transcripts[]", False)]
        assert "transcript" not in consumers

    def test_a_standalone_pipe_batch_maps_the_list_slot_to_its_item_slot(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeBatch"
description = "Extract every transcript"
inputs = { transcripts = "Document[]" }
output = "Page[]"
branch_pipe_code = "extract_pdf"
input_list_name = "transcripts"
input_item_name = "transcript"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_batch", pipes=pipes)

        assert _summary(consumers["transcripts"]) == [("extract_pdf", "transcripts[]", False)]

    def test_every_parallel_branch_is_visited(self, load_empty_library: Callable[[], str]):
        pipes = """
[concept.BothExtractions]
description = "The transcript extracted by two models"

[concept.BothExtractions.structure]
pdf_pages = { type = "list", item_type = "concept", item_concept_ref = "native.Page", description = "Pages read as PDF", required = true }
any_pages = { type = "list", item_type = "concept", item_concept_ref = "native.Page", description = "Pages read by any format", required = true }

[pipe.main]
type = "PipeParallel"
description = "Extract the transcript twice"
inputs = { transcript = "Document" }
output = "BothExtractions"
branches = [
    { pipe = "extract_pdf", result = "pdf_pages" },
    { pipe = "extract_any", result = "any_pages" },
]
add_each_output = true
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_parallel", pipes=pipes)

        assert _summary(consumers["transcript"]) == [("extract_any", "transcript", False), ("extract_pdf", "transcript", False)]

    def test_a_consumer_below_a_condition_is_conditional(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeCondition"
description = "Extract the transcript in one mode only"
inputs = { mode = "Text", transcript = "Document" }
output = "Page[]"
expression = "mode"
default_outcome = "extract_any"

[pipe.main.outcomes]
pdf = "extract_pdf"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_condition", pipes=pipes)

        assert _summary(consumers["transcript"]) == [("extract_any", "transcript", True), ("extract_pdf", "transcript", True)]

    def test_a_liftable_step_is_conditional(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Extract the transcript when there is one"
inputs = { transcript = "Document?" }
output = "Page[]"
steps = [{ pipe = "extract_pdf", result = "pages" }]
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_liftable", pipes=pipes)

        assert _summary(consumers["transcript"]) == [("extract_pdf", "transcript", True)]

    def test_a_nested_sequence_is_followed(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Delegate to an inner sequence"
inputs = { transcript = "Document" }
output = "Page[]"
steps = [{ pipe = "inner", result = "pages" }]

[pipe.inner]
type = "PipeSequence"
description = "Extract the transcript"
inputs = { transcript = "Document" }
output = "Page[]"
steps = [{ pipe = "extract_pdf", result = "inner_pages" }]
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_nested", pipes=pipes)

        assert _summary(consumers["transcript"]) == [("extract_pdf", "transcript", False)]

    def test_pipe_func_and_pipe_compose_are_opaque(self, load_empty_library: Callable[[], str]):
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Hand the transcript to opaque pipes only"
inputs = { transcript = "Document" }
output = "Text"
steps = [
    { pipe = "replace_transcript", result = "other_transcript" },
    { pipe = "compose_note", result = "note" },
]

[pipe.replace_transcript]
type = "PipeFunc"
description = "Replace the transcript with another document"
inputs = { transcript = "Document" }
output = "Document"
function_name = "file_consumers_replace_transcript"

[pipe.compose_note]
type = "PipeCompose"
description = "Compose a note about the transcript"
inputs = { transcript = "Document" }
output = "Text"
template = "A note about $transcript"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_opaque", pipes=pipes)

        assert consumers.get("transcript", []) == []

    def test_an_unresolved_pipe_is_opaque(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """A cross-package reference whose package is not loaded resolves to nothing, and the walk never guesses past it."""
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Extract the transcript"
inputs = { transcript = "Document" }
output = "Page[]"
steps = [{ pipe = "extract_pdf", result = "pages" }]
"""
        mthds_content = _bundle(domain="fic_unresolved", pipes=pipes)
        library_id = load_empty_library()
        get_library_manager().load_from_blueprints(
            library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content)]
        )
        entry_pipe = get_required_pipe(pipe_code="fic_unresolved.main")
        mocker.patch.object(file_input_consumers_module, "get_optional_pipe", return_value=None)

        assert collect_file_input_consumers(entry_pipe) == {}

    def test_a_pipe_llm_consumes_the_documents_its_prompt_references(self, load_empty_library: Callable[[], str]):
        """An item reference reached through a batch, and a list reference: the prompt names each by its variable path."""
        pipes = """
[pipe.main]
type = "PipeSequence"
description = "Summarize every transcript, then compare them all"
inputs = { transcripts = "Document[]" }
output = "Text"
steps = [
    { pipe = "summarize_transcript", batch_over = "transcripts", batch_as = "transcript", result = "summaries" },
    { pipe = "compare_transcripts", result = "comparison" },
]

[pipe.summarize_transcript]
type = "PipeLLM"
description = "Summarize one transcript"
inputs = { transcript = "Document" }
output = "Text"
prompt = "Summarize this transcript: $transcript"

[pipe.compare_transcripts]
type = "PipeLLM"
description = "Compare the transcripts"
inputs = { transcripts = "Document[]", summaries = "Text[]" }
output = "Text"
prompt = "Compare these transcripts: $transcripts, given their summaries: $summaries"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_llm", pipes=pipes)

        assert _summary(consumers["transcripts"]) == [("compare_transcripts", "transcripts", False), ("summarize_transcript", "transcripts[]", False)]
        expected_formats: set[str] = set()
        for llm_setting in (resolve_llm_setting_for_text(), resolve_llm_setting_for_object()):
            for model_spec in file_input_consumers_module.resolve_model_specs(model_reference=llm_setting.model, model_type=ModelType.LLM):
                expected_formats |= model_spec.supported_document_types
        for consumer in consumers["transcripts"]:
            assert consumer.kind == FileConsumerKind.LLM_DOCUMENT
            assert consumer.readable_formats == frozenset(expected_formats)
            assert consumer.covers(file_input_path=("transcripts", 1))
            assert not consumer.covers(file_input_path=("notes", 1))

    def test_a_pipe_judge_consumes_its_document_inputs(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """Every input is material to judge, so a document input is sent as a file whether or not the question names it."""
        model_deck = get_model_deck()
        judgment_model = model_deck.judgment_aliases["default-judgment"]
        booted_spec = model_deck.inference_models[judgment_model]
        mocker.patch.dict(model_deck.inference_models, {judgment_model: booted_spec.model_copy(update={"inputs": ["text", "images", "pdf"]})})
        pipes = """
[pipe.main]
type = "PipeJudge"
description = "Judge whether the claims are complete"
inputs = { claims = "Document[]", note = "Text", photo = "Image" }
output = "YesNo"
model = "@default-judgment"
question = "Are these claims complete, given $note?"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_judge", pipes=pipes)

        assert set(consumers) == {"claims"}
        (consumer,) = consumers["claims"]
        assert consumer.kind == FileConsumerKind.JUDGMENT_DOCUMENT
        assert consumer.model == judgment_model
        assert consumer.readable_formats == frozenset({"pdf"})
        assert consumer.covers(file_input_path=("claims", 0))

    def test_a_waterfall_reads_a_format_when_any_member_reads_it(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        mocker.patch.dict(get_model_deck().extract_waterfalls, {"fic-mixed-extractors": [PDF_ONLY_MODEL, DOCLING_MODEL]})
        pipes = """
[pipe.main]
type = "PipeExtract"
description = "Extract the transcript with a waterfall"
inputs = { transcript = "Document" }
output = "Page[]"
model = "~fic-mixed-extractors"
"""
        consumers = _consumers(load_empty_library=load_empty_library, domain="fic_waterfall", pipes=pipes)

        (consumer,) = consumers["transcript"]
        assert consumer.model == "fic-mixed-extractors"
        assert consumer.readable_formats == DOCLING_FORMATS
