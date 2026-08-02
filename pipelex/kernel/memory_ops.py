"""The memory boundary of a kernel call: shape inputs in, write results back, read results out.

`store_result` is the write-back every operator's kernel ops end with — wrap the produced content in
a `Stuff` and make it the memory's new main stuff — so that ending lives here once rather than at
each domain's ops module. It is also where the memory contract is actually implemented, which is why
a domain module never inlines the two calls: the day the contract stops aliasing argument and return,
exactly one function changes.

`shape_inputs` and the extraction helpers are the boundary's other two ends. They are thin over
machinery that already exists (`InputShaper`, `WorkingMemory`'s typed accessors) and are deliberately
kept that way — the value is not new behavior, it is that a programmatic caller reads the whole
memory boundary off one module whose every function is keyword-only, hub-free and boot-contract
tested, instead of assembling it from a `core/` factory, a `core/` classmethod and two `WorkingMemory`
methods with positional parameters. Both callers of the shaping half go through the same function,
which is the property that stops them drifting.
"""

from pathlib import Path

from mthds.protocol.pipeline_inputs import PipelineInputs

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.concept_provider_abstract import ConceptProviderAbstract
from pipelex.core.memory.input_shaper import InputShaper
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.input_stuff_specs import InputStuffSpecs
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff_content import StuffContent, StuffContentType
from pipelex.core.stuffs.stuff_factory import StuffFactory


def shape_inputs(
    *,
    inputs: PipelineInputs,
    concept_provider: ConceptProviderAbstract,
    input_specs: InputStuffSpecs,
    search_domain_codes: list[str] | None = None,
    inputs_base_dir: Path | None = None,
) -> WorkingMemory:
    """Interpret a caller's raw inputs against their declared specs and return the memory to run on.

    Signature-driven shaping only (Smart Inputs): each value is read top-down against the concept its
    spec declares. `input_specs` is required rather than optional, which is the one place this
    function is narrower than `WorkingMemoryFactory.make_from_pipeline_inputs` — the bottom-up,
    no-signature arm infers a concept from each value's own shape, and inference is exactly the kind
    of ambient guess a kernel entry point should not make on a caller's behalf. A caller with no
    declared specs builds its stuffs directly and hands over a `WorkingMemory`.

    `concept_provider` is taken explicitly, never looked up: resolving concepts is what a loaded
    method's library is for, and the kernel must stay callable without one.

    A malformed input is rejected here with a typed, locator-bearing error rather than coerced — this
    is the boundary where a caller's raw values stop being raw, so it is the right place to refuse.

    Raises:
        UnknownInputNameError: a provided name is not declared in `input_specs` (D8).
        InputShapingError subclasses: a provided value cannot be shaped to its declared concept (D4).
    """
    return InputShaper.shape(
        inputs,
        concept_provider=concept_provider,
        input_specs=input_specs,
        search_domain_codes=search_domain_codes,
        inputs_base_dir=inputs_base_dir,
    )


def store_result(
    *,
    memory: WorkingMemory,
    concept: Concept,
    content: StuffContent,
    result_name: str | None = None,
    result_code: str | None = None,
) -> WorkingMemory:
    """Write a produced content into memory as the new main stuff, and return the memory.

    Returning it is the contract, not a convenience: the argument is mutated today because inline
    execution aliases the two, and a caller that relies on that aliasing breaks the moment a
    serialization boundary sits between them.
    """
    stuff = StuffFactory.make_stuff(concept=concept, content=content, name=result_name, code=result_code)
    memory.set_new_main_stuff(stuff=stuff, name=result_name)
    return memory


def extract_main_content(*, memory: WorkingMemory, content_type: type[StuffContentType]) -> StuffContentType:
    """Read the memory's main stuff as `content_type`.

    This is the typed read of what a kernel call just produced. It is needed even though every result
    envelope already carries the content, because the envelopes annotate that field with the base
    `StuffContent` (`LlmObjectResult.content` and its siblings) — so a caller holding a result has the
    object but not the type. Pass the class you asked the op to produce and get it back narrowed.

    Read from the memory the call **returned**, never from the one you passed in: they alias today and
    the contract says they need not.

    Raises:
        WorkingMemoryStuffNotFoundError: nothing has been stored as main stuff yet.
        StuffContentTypeError: the stored content is not a `content_type`.
    """
    return memory.main_stuff_as(content_type)


def extract_named_content(*, memory: WorkingMemory, name: str, content_type: type[StuffContentType]) -> StuffContentType:
    """Read a named slot as `content_type` — the same typed read as `extract_main_content`, by name.

    Named slots are how a caller reads back anything other than the last result: an input it shaped,
    or an earlier step's output stored under its own `result_name`.

    Raises:
        WorkingMemoryStuffNotFoundError: no stuff (and no alias) under that name.
        StuffContentTypeError: the stored content is not a `content_type`.
    """
    return memory.get_stuff_as(name=name, content_type=content_type)


def extract_main_content_as_list(*, memory: WorkingMemory, item_type: type[StuffContentType]) -> ListContent[StuffContentType]:
    """Read the memory's main stuff as a list of `item_type` — the typed read for a multi-output call.

    A kernel op that produces several objects (`llm_object(is_multiple_output=True)`) stores them as one
    `ListContent`, and the single-content read above cannot narrow that: passing the bare item class
    raises, and passing `ListContent[item_type]` is rejected by design. Without this, the one shape the
    kernel produces that its own read half could not narrow would send the caller back out to
    `WorkingMemory`'s positional accessors — and the bare-`ListContent` workaround loses the item type,
    which is the whole point of asking.

    Every item is verified against `item_type`, so the returned list is typed all the way down.

    Raises:
        WorkingMemoryStuffNotFoundError: nothing has been stored as main stuff yet.
        StuffContentTypeError: the stored content is not a list, or an item is not an `item_type`.
    """
    return memory.main_stuff_as_list(item_type)


def extract_named_content_as_list(*, memory: WorkingMemory, name: str, item_type: type[StuffContentType]) -> ListContent[StuffContentType]:
    """Read a named slot as a list of `item_type` — the same typed read as `extract_main_content_as_list`, by name.

    Raises:
        WorkingMemoryStuffNotFoundError: no stuff (and no alias) under that name.
        StuffContentTypeError: the stored content is not a list, or an item is not an `item_type`.
    """
    return memory.get_stuff_as_list(name, item_type=item_type)
