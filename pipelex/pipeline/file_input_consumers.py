"""Which operators will consume each input slot's files, found by walking the entry pipe statically.

Run setup uses it to refuse, before the run starts, a file input that is certain to reach a consumer
that cannot read its format. The walk starts from the entry pipe's input slots and follows them by
name through the controllers, the way the absence-taint analysis does (`PipeSequence.analyze_taint`),
resolving sub-pipes through the hub:

- **Sequence.** Steps are visited in order, and a slot a step overwrites stops being followed after
  that step. A step overwrites its result's name, and also whatever a nested sequence or condition
  outcome writes, since those run on the caller's memory; after a step that may write a name the
  walk cannot know, nothing more is followed. A step's batch parameters map the list slot to its
  item slot. A binding step makes its result stand for where the value it binds comes from: a single
  value, or the list one field of a single root holds, for the entry path it reads, a renamed copy
  for its root's own path, and a list gathered across items whose last field is itself a list for
  every item of that field, `cases[].transcripts` for `cases.transcripts` over a list root. A list
  gathered from a field that is not a list, `cases.attachment`, has no path a frame can say, so its
  result stops being followed. A dotted `batch_over` is such a binding followed by a batch over its
  result.
- **Parallel.** Every branch is visited.
- **Batch.** The list slot maps to the item slot, and the branch pipe is visited.
- **Condition.** Every outcome is visited, and whatever is found below it is conditional.
- **Liftable steps.** A step the absence-taint analysis marks as liftable may be skipped, so what it
  consumes is conditional too. The analysis's own verdicts are reused, never re-derived.
- **Opaque pipes.** A `PipeFunc`, a `PipeCompose`, a search pipe, any other operator, and an
  unresolved cross-package reference consume nothing as far as the walk knows: it never guesses.
- **Consumers.** A `PipeExtract` consumes its document input, and reads the formats of the model its
  extract choice resolves to. A `PipeLLM` consumes the documents its prompt references by variable
  path, and reads its resolved model's document types. A `PipeJudge` consumes the documents its prompt
  references by variable path, as a PipeLLM does, and reads its resolved judgment model's document
  types. A waterfall reads a format when any of its members reads it.

The walk depends only on the library and the model deck, never on the input values.
"""

from enum import StrEnum
from typing import Final, NamedTuple

from pydantic import BaseModel, ConfigDict

from pipelex.cogt.exceptions import JudgmentModelMissingError, ModelChoiceNotFoundError
from pipelex.cogt.model_backends.model_spec import InferenceModelSpec
from pipelex.cogt.model_backends.model_type import ModelType
from pipelex.cogt.models.exceptions import ModelReferenceParseError
from pipelex.cogt.models.model_reference import ModelReference, ModelReferenceKind
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.interpreter_hub import get_concept_library, get_native_concept, get_optional_pipe
from pipelex.kernel.extract_ops import resolve_extract_setting
from pipelex.kernel.judgment_ops import judgment_setting_of_choice
from pipelex.kernel.llm_ops import resolve_llm_setting_for_object, resolve_llm_setting_for_text
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_controllers.parallel.pipe_parallel import PipeParallel
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_operators.extract.pipe_extract import PipeExtract
from pipelex.pipe_operators.judge.pipe_judge import PipeJudge
from pipelex.pipe_operators.llm.pipe_llm import PipeLLM
from pipelex.pipe_run.pipe_run_params import BatchParams
from pipelex.pipeline.exceptions import PipelineInputFormatUnsupportedError
from pipelex.pipeline.input_normalizer import IdentifiedFileInput
from pipelex.runtime_hub import get_model_deck
from pipelex.tools.misc.filetype_utils import describe_file_format, describe_format_keys
from pipelex.tools.uri.resolved_uri import UriKind

# The segment of a consumed path that stands for any item of a list: `("transcripts", "[]")`
# is every item of `transcripts`. A field name never contains brackets, so it cannot collide.
LIST_ITEM_SEGMENT: Final[str] = "[]"

# A model reference resolves through presets, aliases and waterfalls in a handful of hops; this
# only stops a malformed deck that points a reference back at itself.
_MAX_PRESET_HOPS: Final[int] = 8

# How a refusal names a web-page model's declaration among the formats it reads.
_WEB_PAGE_INPUT: Final[str] = "web_page"

# What a variable of the current frame stands for: the path, from an entry input slot, of the
# value it holds. `{"transcript": ("transcripts", "[]")}` inside a batch over `transcripts`.
_Frame = dict[str, tuple[str, ...]]


class FileConsumerKind(StrEnum):
    """How an operator consumes a file."""

    EXTRACT = "extract"
    LLM_DOCUMENT = "llm_document"
    JUDGMENT_DOCUMENT = "judgment_document"

    @property
    def model_type(self) -> ModelType:
        match self:
            case FileConsumerKind.EXTRACT:
                return ModelType.TEXT_EXTRACTOR
            case FileConsumerKind.LLM_DOCUMENT:
                return ModelType.LLM
            case FileConsumerKind.JUDGMENT_DOCUMENT:
                return ModelType.JUDGMENT


class FileInputConsumer(BaseModel):
    """One operator that consumes the files of an entry input slot, with what its model reads."""

    model_config = ConfigDict(frozen=True)

    slot_name: str
    """The entry pipe's input slot the files come from."""

    consumed_path: tuple[str, ...]
    """The path, from the slot, of what the operator consumes: `("transcripts", "[]")` is every item."""

    pipe_ref: str
    pipe_code: str
    kind: FileConsumerKind

    model: str | None
    """The model the consumer resolves to: a concrete handle, or the waterfall it names. `None` when unresolved."""

    readable_formats: frozenset[str] | None
    """The format keys the model reads; `None` when the model could not be resolved, which makes the consumer opaque."""

    reads_web_pages: bool
    """Whether the model fetches a web page itself from an http(s) URL, which is then not format-checked."""

    is_conditional: bool
    """Whether the consumer is reached through a condition or a liftable step, so it may not run at all."""

    @property
    def model_type(self) -> ModelType:
        return self.kind.model_type

    @property
    def display_consumed_path(self) -> str:
        """The consumed path as a caller reads it: `transcripts[]`, `case.attachment`."""
        rendered = ""
        for segment in self.consumed_path:
            if segment == LIST_ITEM_SEGMENT:
                rendered += LIST_ITEM_SEGMENT
            elif rendered:
                rendered += f".{segment}"
            else:
                rendered = segment
        return rendered

    @property
    def listed_formats(self) -> set[str]:
        """What a refusal says the model reads: its file formats, and web pages when it fetches them."""
        listed_formats = set(self.readable_formats or ())
        if self.reads_web_pages:
            listed_formats.add(_WEB_PAGE_INPUT)
        return listed_formats

    @property
    def verb_phrase(self) -> str:
        """How a refusal says what the pipe does with the file."""
        match self.kind:
            case FileConsumerKind.EXTRACT:
                return "extracts it with"
            case FileConsumerKind.LLM_DOCUMENT | FileConsumerKind.JUDGMENT_DOCUMENT:
                return "gives it to"

    def covers(self, *, file_input_path: tuple[str | int, ...]) -> bool:
        """Whether a file at this path in the inputs is among what the consumer consumes.

        A list index matches the item segment, and a consumed path covers everything below it, so
        `transcripts` covers `transcripts[2]` and `case` covers `case.attachment`.
        """
        normalized_path = tuple(LIST_ITEM_SEGMENT if isinstance(segment, int) else segment for segment in file_input_path)
        return normalized_path[: len(self.consumed_path)] == self.consumed_path


class _ResolvedModel(NamedTuple):
    """What a consumer's model reference resolved to."""

    model: str
    specs: list[InferenceModelSpec]


def collect_file_input_consumers(entry_pipe: PipeAbstract) -> dict[str, list[FileInputConsumer]]:
    """For each input slot of the entry pipe, the operators that will consume its files.

    Must run while the pipe's library is loaded: sub-pipes are resolved through the hub, and models
    through the model deck. A slot that reaches no consumer has no entry.

    Args:
        entry_pipe: The pipe a run starts from.

    Returns:
        The consumers, by entry input slot name, in the order the walk found them.
    """
    frame: _Frame = {input_name: (input_name,) for input_name in entry_pipe.inputs.root}
    consumers: list[FileInputConsumer] = []
    _visit(pipe=entry_pipe, frame=frame, is_conditional=False, visiting=frozenset(), consumers=consumers)
    consumers_by_slot: dict[str, list[FileInputConsumer]] = {}
    for consumer in consumers:
        consumers_by_slot.setdefault(consumer.slot_name, []).append(consumer)
    return consumers_by_slot


def check_file_inputs_against_consumers(*, entry_pipe: PipeAbstract, file_inputs: list[IdentifiedFileInput]) -> None:
    """Refuse a run whose file inputs are certain to reach a consumer that cannot read their format.

    Each file input with a known format is compared with the certain consumers that cover it: a
    consumer reached through a condition or a liftable step may never run, and one whose model could
    not be resolved is opaque, so both are left to the operator's own check. A web-page model given
    an http(s) URL fetches the page itself, so it is not compared. Every violation is collected and
    reported together.

    Args:
        entry_pipe: The pipe the run starts from. Its library must be loaded.
        file_inputs: The run's file inputs with the formats run setup established
            (`collect_file_inputs`).

    Raises:
        PipelineInputFormatUnsupportedError: If any file input is certain to reach a consumer whose
            model does not read its format.
    """
    known_file_inputs = [file_input for file_input in file_inputs if file_input.format_key is not None]
    if not known_file_inputs:
        return
    consumers_by_slot = collect_file_input_consumers(entry_pipe)
    violations: list[str] = []
    for file_input in known_file_inputs:
        format_key = file_input.format_key
        if format_key is None:
            continue
        slot_name = str(file_input.path[0])
        for consumer in consumers_by_slot.get(slot_name, []):
            if consumer.is_conditional or consumer.readable_formats is None or not consumer.covers(file_input_path=file_input.path):
                continue
            if consumer.reads_web_pages and _is_http_url(uri_kind=file_input.uri_kind):
                continue
            if format_key in consumer.readable_formats:
                continue
            violations.append(
                f"Input '{file_input.display_path}' is {describe_file_format(format_key=format_key, mime_type=file_input.mime_type)}: "
                f"pipe '{consumer.pipe_code}' {consumer.verb_phrase} model '{consumer.model}', "
                f"which reads {describe_format_keys(format_keys=consumer.listed_formats)}."
            )
    if violations:
        msg = " ".join([*violations, "Give a file in a format its model reads, or use a model that reads this format."])
        raise PipelineInputFormatUnsupportedError(msg)


def _is_http_url(*, uri_kind: UriKind) -> bool:
    match uri_kind:
        case UriKind.HTTP_URL:
            return True
        case UriKind.LOCAL_PATH | UriKind.PIPELEX_STORAGE | UriKind.BASE64_DATA_URL:
            return False


def resolve_model_specs(*, model_reference: str, model_type: ModelType) -> list[InferenceModelSpec]:
    """The model specs a model reference can be served by: one for a handle or an alias, every available member for a waterfall.

    A preset is not resolved here: the caller resolves a step's choice to a setting first. A member
    the deck does not serve (its backend is disabled) is skipped, since no run could use it either.
    An unresolvable reference gives no spec.
    """
    return _resolve_model_specs(model_reference=model_reference, model_type=model_type, visited=frozenset())


def _resolve_model_specs(*, model_reference: str, model_type: ModelType, visited: frozenset[str]) -> list[InferenceModelSpec]:
    if model_reference in visited:
        return []
    visited |= {model_reference}
    try:
        reference = ModelReference.parse(model_reference)
    except ModelReferenceParseError:
        return []
    model_deck = get_model_deck()
    aliases, waterfalls = model_deck.get_aliases_and_waterfalls_for_type(model_type)
    alias_target: str | None = None
    waterfall_members: list[str] | None = None
    match reference.kind:
        case ModelReferenceKind.PRESET:
            return []
        case ModelReferenceKind.ALIAS:
            alias_target = aliases.get(reference.name)
        case ModelReferenceKind.WATERFALL:
            waterfall_members = waterfalls.get(reference.name)
        case ModelReferenceKind.HANDLE:
            # A handle served as another type only does not stop the lookup: this type's alias or
            # waterfall of the same name is tried next, as the deck's own lookup does.
            if model_spec := model_deck.inference_models.get(model_type=model_type, handle=reference.name):
                return [model_spec]
            alias_target = aliases.get(reference.name)
            waterfall_members = None if alias_target else waterfalls.get(reference.name)
    if alias_target:
        return _resolve_model_specs(model_reference=alias_target, model_type=model_type, visited=visited)
    model_specs: list[InferenceModelSpec] = []
    for member in waterfall_members or []:
        model_specs.extend(_resolve_model_specs(model_reference=member, model_type=model_type, visited=visited))
    return model_specs


def _visit(*, pipe: PipeAbstract, frame: _Frame, is_conditional: bool, visiting: frozenset[str], consumers: list[FileInputConsumer]) -> None:
    """Visit one pipe with the frame of tracked variables it sees, recording the consumers it holds."""
    if pipe.visit_key in visiting or not frame:
        return
    visiting |= {pipe.visit_key}
    if isinstance(pipe, PipeSequence):
        _visit_sequence(sequence=pipe, frame=frame, is_conditional=is_conditional, visiting=visiting, consumers=consumers)
    elif isinstance(pipe, PipeParallel):
        liftable_refs = {liftable_step.pipe_ref for liftable_step in pipe.analyze_branch_taint().liftable_steps}
        for sub_pipe in pipe.parallel_sub_pipes:
            _visit_sub_pipe(
                sub_pipe=sub_pipe, frame=frame, is_conditional=is_conditional, liftable_refs=liftable_refs, visiting=visiting, consumers=consumers
            )
    elif isinstance(pipe, PipeBatch):
        if branch_pipe := get_optional_pipe(pipe_code=pipe.branch_pipe_code):
            _visit(
                pipe=branch_pipe,
                frame=_batch_frame(frame=frame, batch_params=pipe.batch_params),
                is_conditional=is_conditional,
                visiting=visiting,
                consumers=consumers,
            )
    elif isinstance(pipe, PipeCondition):
        for outcome_pipe_code in sorted(pipe.pipe_dependencies()):
            if outcome_pipe := get_optional_pipe(pipe_code=outcome_pipe_code):
                _visit(pipe=outcome_pipe, frame=frame, is_conditional=True, visiting=visiting, consumers=consumers)
    elif isinstance(pipe, PipeExtract):
        _record_extract_consumer(pipe_extract=pipe, frame=frame, is_conditional=is_conditional, consumers=consumers)
    elif isinstance(pipe, PipeLLM):
        _record_llm_document_consumers(pipe_llm=pipe, frame=frame, is_conditional=is_conditional, consumers=consumers)
    elif isinstance(pipe, PipeJudge):
        _record_judgment_document_consumers(pipe_judge=pipe, frame=frame, is_conditional=is_conditional, consumers=consumers)


def _visit_sequence(
    *, sequence: PipeSequence, frame: _Frame, is_conditional: bool, visiting: frozenset[str], consumers: list[FileInputConsumer]
) -> None:
    liftable_refs = {liftable_step.pipe_ref for liftable_step in sequence.analyze_taint().liftable_steps}
    typed_flow = sequence.build_typed_flow() if any(isinstance(step, BindingStep) for step in sequence.sequential_sub_pipes) else None
    step_frame = dict(frame)
    for step_index, sub_pipe in enumerate(sequence.sequential_sub_pipes):
        if isinstance(sub_pipe, BindingStep):
            # A binding stores a copy of the value at its path, and its result stands for where that value comes from, built
            # on the path its root stands for: a single value, a renamed copy or one list field of a single root is at the
            # entry path it reads, and a list whose last field is itself a list, gathered across the items of a list root or
            # of a list crossed before it, holds the items of that field, `("cases", "[]", "transcripts")` for
            # `cases.transcripts` over a list root. A batch over the result, a dotted `batch_over` included, then maps its
            # item to that path followed by the item segment, which covers a file at `cases[1].transcripts[0]`. A list
            # gathered from a field that is not a list, `cases.attachment`, holds values sitting at `cases[].attachment`
            # rather than at the items of one path, which a frame cannot say, since it maps a slot to the value at one path
            # and a batch's item to that path's items, so its result stops being followed.
            derivation = typed_flow.binding_derivations.get(step_index) if typed_flow is not None else None
            root_path = step_frame.get(sub_pipe.root_name)
            provenance_path = derivation.provenance_path(item_segment=LIST_ITEM_SEGMENT) if derivation is not None else None
            if root_path is None or provenance_path is None:
                step_frame.pop(sub_pipe.output_name, None)
            else:
                step_frame[sub_pipe.output_name] = (*root_path, *provenance_path)
            continue
        step_pipe = _visit_sub_pipe(
            sub_pipe=sub_pipe, frame=step_frame, is_conditional=is_conditional, liftable_refs=liftable_refs, visiting=visiting, consumers=consumers
        )
        # Whatever the step writes into the flow overwrites the slot of that name: later steps read
        # the step's result there, not the input, so it stops being followed.
        step_writes = _sub_pipe_writes(sub_pipe=sub_pipe, step_pipe=step_pipe, visiting=frozenset())
        if step_writes.may_write_any:
            return
        for written_name in step_writes.names:
            step_frame.pop(written_name, None)


class _Writes(NamedTuple):
    """The names a step may write into the working memory of the sequence that runs it."""

    names: frozenset[str]
    may_write_any: bool
    """Whether it may write a name the walk cannot know statically, after which nothing is followed."""


_NO_WRITES: Final[_Writes] = _Writes(names=frozenset(), may_write_any=False)
_ANY_WRITES: Final[_Writes] = _Writes(names=frozenset(), may_write_any=True)


def _sub_pipe_writes(*, sub_pipe: SubPipe, step_pipe: PipeAbstract | None, visiting: frozenset[str]) -> _Writes:
    """What a controller's step writes into the memory it runs on: its result, and whatever its pipe writes there.

    A batched step runs every item on a copy of the memory, and only its result comes back.
    """
    result_names = frozenset({sub_pipe.output_name}) if sub_pipe.output_name else frozenset[str]()
    if sub_pipe.batch_params:
        return _Writes(names=result_names, may_write_any=False)
    if step_pipe is None:
        return _ANY_WRITES
    pipe_writes = _pipe_writes(pipe=step_pipe, visiting=visiting)
    return _Writes(names=result_names | pipe_writes.names, may_write_any=pipe_writes.may_write_any)


def _pipe_writes(*, pipe: PipeAbstract, visiting: frozenset[str]) -> _Writes:
    """What a pipe writes into the memory it runs on, besides its own result, which its caller names.

    A sequence runs its steps on that memory and a condition runs its outcome on it, so what they
    write lands in the caller's memory too. A parallel runs its branches on copies and writes back
    only its branch results, when it adds each of them. A batch runs on copies. An operator writes
    only its result.
    """
    if pipe.visit_key in visiting:
        return _NO_WRITES
    visiting |= {pipe.visit_key}
    if isinstance(pipe, PipeSequence):
        return _merge_writes(
            writes=[
                _Writes(names=frozenset({sub_pipe.output_name}), may_write_any=False)
                if isinstance(sub_pipe, BindingStep)
                else _sub_pipe_writes(sub_pipe=sub_pipe, step_pipe=get_optional_pipe(pipe_code=sub_pipe.pipe_code), visiting=visiting)
                for sub_pipe in pipe.sequential_sub_pipes
            ]
        )
    if isinstance(pipe, PipeCondition):
        # The alias a condition adds is named after the value its expression renders to.
        if pipe.add_alias_from_expression_to:
            return _ANY_WRITES
        outcome_writes: list[_Writes] = []
        for outcome_pipe_code in pipe.pipe_dependencies():
            outcome_pipe = get_optional_pipe(pipe_code=outcome_pipe_code)
            outcome_writes.append(_pipe_writes(pipe=outcome_pipe, visiting=visiting) if outcome_pipe else _ANY_WRITES)
        return _merge_writes(writes=outcome_writes)
    if isinstance(pipe, PipeParallel) and pipe.add_each_output:
        return _Writes(names=frozenset(branch.output_name for branch in pipe.parallel_sub_pipes if branch.output_name), may_write_any=False)
    return _NO_WRITES


def _merge_writes(*, writes: list[_Writes]) -> _Writes:
    return _Writes(
        names=frozenset[str]().union(*(step_writes.names for step_writes in writes)),
        may_write_any=any(step_writes.may_write_any for step_writes in writes),
    )


def _visit_sub_pipe(
    *,
    sub_pipe: SubPipe,
    frame: _Frame,
    is_conditional: bool,
    liftable_refs: set[str],
    visiting: frozenset[str],
    consumers: list[FileInputConsumer],
) -> PipeAbstract | None:
    """Visit a controller's step or branch, returning the pipe it resolved to, `None` when unresolved."""
    step_pipe = get_optional_pipe(pipe_code=sub_pipe.pipe_code)
    if step_pipe is None:
        return None
    step_frame = _batch_frame(frame=frame, batch_params=sub_pipe.batch_params) if sub_pipe.batch_params else frame
    _visit(
        pipe=step_pipe,
        frame=step_frame,
        is_conditional=is_conditional or step_pipe.pipe_ref in liftable_refs,
        visiting=visiting,
        consumers=consumers,
    )
    return step_pipe


def _batch_frame(*, frame: _Frame, batch_params: BatchParams) -> _Frame:
    """The frame a batch's branch sees: the item slot stands for an item of the list slot, when that is tracked."""
    batch_frame = dict(frame)
    batch_frame.pop(batch_params.input_item_stuff_name, None)
    if list_path := _tracked_path(frame=frame, variable_path=batch_params.input_list_stuff_name):
        batch_frame[batch_params.input_item_stuff_name] = (*list_path, LIST_ITEM_SEGMENT)
    return batch_frame


def _tracked_path(*, frame: _Frame, variable_path: str) -> tuple[str, ...] | None:
    """The entry path a dotted variable path stands for, when its root is tracked: `case.attachment` → `("case", "attachment")`."""
    root_name, *field_names = variable_path.split(".")
    if root_path := frame.get(root_name):
        return (*root_path, *field_names)
    return None


def _record_extract_consumer(*, pipe_extract: PipeExtract, frame: _Frame, is_conditional: bool, consumers: list[FileInputConsumer]) -> None:
    # An Image input is an image by the setup check, and an extractor that reads no images is the
    # method author's choice of model, not the caller's input: only a document input is followed.
    if not pipe_extract.document_stuff_name:
        return
    consumed_path = _tracked_path(frame=frame, variable_path=pipe_extract.document_stuff_name)
    if consumed_path is None:
        return
    resolved_model = _resolve_extract_model(pipe_extract=pipe_extract)
    readable_formats: frozenset[str] | None = None
    reads_web_pages = False
    if resolved_model is not None:
        readable_formats = frozenset[str]().union(*(model_spec.readable_formats_for_extract for model_spec in resolved_model.specs))
        reads_web_pages = any(model_spec.is_web_page_supported_for_extract for model_spec in resolved_model.specs)
    consumers.append(
        FileInputConsumer(
            slot_name=consumed_path[0],
            consumed_path=consumed_path,
            pipe_ref=pipe_extract.pipe_ref,
            pipe_code=pipe_extract.code,
            kind=FileConsumerKind.EXTRACT,
            model=resolved_model.model if resolved_model else None,
            readable_formats=readable_formats,
            reads_web_pages=reads_web_pages,
            is_conditional=is_conditional,
        )
    )


def _record_llm_document_consumers(*, pipe_llm: PipeLLM, frame: _Frame, is_conditional: bool, consumers: list[FileInputConsumer]) -> None:
    prompt_spec = pipe_llm.llm_prompt_spec
    document_references = [*(prompt_spec.user_document_references or []), *(prompt_spec.system_document_references or [])]
    if not document_references:
        return
    resolved_model = _resolve_llm_model(pipe_llm=pipe_llm)
    readable_formats: frozenset[str] | None = None
    if resolved_model is not None:
        readable_formats = frozenset[str]().union(*(model_spec.supported_document_types for model_spec in resolved_model.specs))
    # A model that reads no documents at all is the method author's choice of model, which the
    # worker reports as a capability error: there is no caller's format to refuse.
    if not readable_formats:
        return
    for document_reference in document_references:
        consumed_path = _tracked_path(frame=frame, variable_path=document_reference.variable_path)
        if consumed_path is None:
            continue
        consumers.append(
            FileInputConsumer(
                slot_name=consumed_path[0],
                consumed_path=consumed_path,
                pipe_ref=pipe_llm.pipe_ref,
                pipe_code=pipe_llm.code,
                kind=FileConsumerKind.LLM_DOCUMENT,
                model=resolved_model.model if resolved_model else None,
                readable_formats=readable_formats,
                reads_web_pages=False,
                is_conditional=is_conditional,
            )
        )


def _record_judgment_document_consumers(*, pipe_judge: PipeJudge, frame: _Frame, is_conditional: bool, consumers: list[FileInputConsumer]) -> None:
    # The prompt presents the documents it references, as a PipeLLM's does, and an input reaches the
    # judging model only through a template, so a document input the prompt does not reference is not
    # sent: only the prompt's references are followed.
    document_references = pipe_judge.prompt_content.document_references or []
    if not document_references:
        return
    resolved_model = _resolve_judgment_model(pipe_judge=pipe_judge)
    readable_formats: frozenset[str] | None = None
    if resolved_model is not None:
        readable_formats = frozenset[str]().union(*(model_spec.supported_document_types for model_spec in resolved_model.specs))
    # A model that reads no documents at all is the method author's choice of model, which the
    # method's load refuses: there is no caller's format to refuse.
    if not readable_formats:
        return
    for document_reference in document_references:
        consumed_path = _tracked_path(frame=frame, variable_path=document_reference.variable_path)
        if consumed_path is None:
            continue
        consumers.append(
            FileInputConsumer(
                slot_name=consumed_path[0],
                consumed_path=consumed_path,
                pipe_ref=pipe_judge.pipe_ref,
                pipe_code=pipe_judge.code,
                kind=FileConsumerKind.JUDGMENT_DOCUMENT,
                model=resolved_model.model if resolved_model else None,
                readable_formats=readable_formats,
                reads_web_pages=False,
                is_conditional=is_conditional,
            )
        )


def _resolve_judgment_model(*, pipe_judge: PipeJudge) -> _ResolvedModel | None:
    """The model a PipeJudge's choice resolves to, through the deck chain and any preset, `None` when unresolvable."""
    try:
        model_reference = judgment_setting_of_choice(judgment_choice=pipe_judge.judgment_choice, pipe_code=pipe_judge.code).model
    except (JudgmentModelMissingError, ModelChoiceNotFoundError, ModelReferenceParseError):
        return None
    return _resolved_model(model_reference=model_reference, model_type=ModelType.JUDGMENT)


def _resolve_extract_model(*, pipe_extract: PipeExtract) -> _ResolvedModel | None:
    """The model a PipeExtract's choice resolves to, through the deck chain and any preset, `None` when unresolvable."""
    model_deck = get_model_deck()
    try:
        model_reference = resolve_extract_setting(extract_choice=pipe_extract.extract_choice).model
        for _hop in range(_MAX_PRESET_HOPS):
            if not _is_preset(model_reference=model_reference):
                break
            model_reference = model_deck.get_extract_setting(extract_choice=model_reference).model
    except (ModelChoiceNotFoundError, ModelReferenceParseError):
        return None
    return _resolved_model(model_reference=model_reference, model_type=ModelType.TEXT_EXTRACTOR)


def _resolve_llm_model(*, pipe_llm: PipeLLM) -> _ResolvedModel | None:
    """The model a PipeLLM's documents reach, `None` when unresolvable.

    Which of its two settings serves the prompt depends on its output: a single text goes to the
    text setting, anything else to the object setting. A text output can still be generated as a
    list when a step asks for several, so a pipe whose output is text reaches both, and reads a
    format when either model reads it.
    """
    llm_for_text_choice = pipe_llm.llm_choices.for_text if pipe_llm.llm_choices else None
    llm_for_object_choice = pipe_llm.llm_choices.for_object if pipe_llm.llm_choices else None
    try:
        object_model = resolve_llm_setting_for_object(llm_choice=llm_for_object_choice, llm_choice_for_text=llm_for_text_choice).model
        model_references = [object_model]
        if get_concept_library().is_compatible(
            tested_concept=pipe_llm.output.concept,
            wanted_concept=get_native_concept(native_concept=NativeConceptCode.TEXT),
            strict=True,
        ):
            text_model = resolve_llm_setting_for_text(llm_choice=llm_for_text_choice).model
            model_references = [text_model] if text_model == object_model else [text_model, object_model]
        model_references = [_resolve_llm_presets(model_reference=model_reference) for model_reference in model_references]
    except (ModelChoiceNotFoundError, ModelReferenceParseError):
        return None
    model_specs: list[InferenceModelSpec] = []
    for model_reference in model_references:
        model_specs.extend(resolve_model_specs(model_reference=model_reference, model_type=ModelType.LLM))
    if not model_specs:
        return None
    return _ResolvedModel(model=_display_model(model_references=model_references, model_specs=model_specs), specs=model_specs)


def _resolve_llm_presets(*, model_reference: str) -> str:
    model_deck = get_model_deck()
    for _hop in range(_MAX_PRESET_HOPS):
        if not _is_preset(model_reference=model_reference):
            break
        model_reference = model_deck.get_llm_setting(llm_choice=model_reference).model
    return model_reference


def _is_preset(*, model_reference: str) -> bool:
    match ModelReference.parse(model_reference).kind:
        case ModelReferenceKind.PRESET:
            return True
        case ModelReferenceKind.ALIAS | ModelReferenceKind.WATERFALL | ModelReferenceKind.HANDLE:
            return False


def _resolved_model(*, model_reference: str, model_type: ModelType) -> _ResolvedModel | None:
    model_specs = resolve_model_specs(model_reference=model_reference, model_type=model_type)
    if not model_specs:
        return None
    return _ResolvedModel(model=_display_model(model_references=[model_reference], model_specs=model_specs), specs=model_specs)


def _display_model(*, model_references: list[str], model_specs: list[InferenceModelSpec]) -> str:
    """How a message names the model: its concrete handle when there is one, else the references as written."""
    spec_names = sorted({model_spec.name for model_spec in model_specs})
    if len(spec_names) == 1:
        return spec_names[0]
    return " or ".join(model_references)
