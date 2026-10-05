"""The runtime binding step: binds the value at a path in working memory to a new name, inside a PipeSequence.

A binding step is not a pipe. The sequence holding it derives what it binds from its typed flow (the root's
concept walked through the declared structures, `binding_derivation`) and hands the derivation to `bind`,
which reads the root in working memory and stores the result under its own name:

- a root holding a recorded absence lifts the step, as an absent plain input lifts a pipe: a single result
  is recorded as a `SKIPPED` absence chained to the root's record, and a list result is an empty list;
- a single result whose path reaches nothing is recorded as a `DECLARED_ABSENT` absence naming the segment
  that held nothing;
- anything else is a deep copy of the value at the path, stored as a fresh stuff, of the derived concept,
  with a fresh stuff code, for which the binding is the producer in the execution graph.
"""

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.concepts.concept import Concept
from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.pipes.inputs.exceptions import PipeRunInputsError
from pipelex.core.stuffs.list_content import ListContent
from pipelex.core.stuffs.stuff import Stuff
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.stuff_factory import StuffFactory
from pipelex.graph.graph_tracer_manager import GraphTracerManager
from pipelex.graph.graphspec import NodeKind
from pipelex.graph.stuff_io_spec import make_stuff_io_spec
from pipelex.pipe_controllers.binding.binding_derivation import BindingDerivation
from pipelex.pipe_controllers.binding.binding_value import FoundNothing, bind_content
from pipelex.system.job_metadata import JobMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tools.misc.string_utils import get_root_from_dotted_path

# The pipe type a binding node carries in the execution graph, beside its `binding` node kind.
BINDING_NODE_PIPE_TYPE = "BindingStep"


class BindingOutcome(BaseModel):
    """What one binding step stored: the bound stuff, or the absence it recorded."""

    model_config = ConfigDict(frozen=True)

    stuff: Stuff | None = None
    absence: AbsenceRecord | None = None

    @property
    def is_skipped(self) -> bool:
        return self.absence is not None and self.absence.kind.is_skipped


class BindingStep(BaseModel):
    """A PipeSequence step binding the value at `from_path` to `output_name`, as the runtime holds it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    from_path: str
    output_name: str

    @property
    def root_name(self) -> str:
        return get_root_from_dotted_path(self.from_path)

    @property
    def as_written(self) -> str:
        """The step as MTHDS writes it, for messages."""
        return f'{{ from = "{self.from_path}", result = "{self.output_name}" }}'

    def bind(
        self,
        *,
        working_memory: WorkingMemory,
        derivation: BindingDerivation,
        result_concept: Concept,
        calling_pipe_code: str,
        run_mode: PipeRunMode,
        stuff_code: str | None = None,
    ) -> BindingOutcome:
        """Bind the value at the path into `working_memory`, as the main stuff, or record why nothing was bound.

        Args:
            working_memory: The sequence's working memory, written in place.
            derivation: What the step binds, derived from the sequence's typed flow.
            result_concept: The derived concept, resolved in the library.
            calling_pipe_code: The sequence holding the step, for messages and provenance.
            run_mode: The run mode, for the error raised on a missing root.
            stuff_code: The stuff code to give the result, when the run fixes it; a fresh one otherwise.

        Raises:
            PipeRunInputsError: When the root holds neither a value nor a recorded absence.
        """
        root_stuff = working_memory.get_optional_stuff(self.root_name)
        if root_stuff is None:
            root_absence = working_memory.get_optional_absence(self.root_name)
            if root_absence is None:
                msg = (
                    f"The binding step {self.as_written} of pipe '{calling_pipe_code}' reads '{self.root_name}', which is not in working "
                    f"memory and has no recorded absence. Valid keys are: {working_memory.list_keys()}"
                )
                raise PipeRunInputsError(
                    message=msg,
                    run_mode=run_mode,
                    pipe_code=calling_pipe_code,
                    variable_name=self.root_name,
                    concept_code=None,
                )
            return self._lift(
                working_memory=working_memory,
                derivation=derivation,
                result_concept=result_concept,
                root_absence=root_absence,
                stuff_code=stuff_code,
            )

        bound_content = bind_content(root_content=root_stuff.content, derivation=derivation)
        if isinstance(bound_content, FoundNothing):
            record = AbsenceRecord(
                variable_name=self.output_name,
                kind=AbsenceKind.DECLARED_ABSENT,
                reason=(
                    f"the binding step {self.as_written} of pipe '{calling_pipe_code}' bound nothing, "
                    f"because '{bound_content.empty_path}' holds nothing"
                ),
            )
            working_memory.record_new_main_absence(record)
            log.verbose(f"Binding '{self.from_path}' found nothing at '{bound_content.empty_path}': '{self.output_name}' is recorded absent")
            return BindingOutcome(absence=record)

        # A bare name binds a renamed copy of the whole value, which keeps the concept the value has.
        concept = root_stuff.concept if derivation.is_bare_name else result_concept
        bound_stuff = StuffFactory.make_stuff(concept=concept, content=bound_content, name=self.output_name, code=stuff_code)
        working_memory.set_new_main_stuff(bound_stuff, name=self.output_name)
        log.verbose(f"Bound '{self.from_path}' to '{self.output_name}': {concept.concept_ref}")
        return BindingOutcome(stuff=bound_stuff)

    def _lift(
        self,
        *,
        working_memory: WorkingMemory,
        derivation: BindingDerivation,
        result_concept: Concept,
        root_absence: AbsenceRecord,
        stuff_code: str | None,
    ) -> BindingOutcome:
        """Skip the binding because its root is absent, as an absent plain input lifts a pipe.

        A single result is recorded as a skipped absence chained to the root's record; a list result is an empty
        list, since a plural slot is never absent, with the skip kept as a note for observability. The empty list
        takes the stuff code the run fixes, when it fixes one, as a bound value would.
        """
        record = AbsenceRecord(
            variable_name=self.output_name,
            kind=AbsenceKind.SKIPPED,
            reason=f"skipped because input '{self.root_name}' is absent",
            upstream=root_absence,
        )
        if derivation.is_plural:
            empty_list_stuff = StuffFactory.make_stuff(
                concept=result_concept,
                content=ListContent[StuffContent](items=[]),
                name=self.output_name,
                code=stuff_code,
            )
            working_memory.set_new_main_stuff(empty_list_stuff, name=self.output_name)
            working_memory.record_absence(record)
            return BindingOutcome(stuff=empty_list_stuff, absence=record)
        working_memory.record_new_main_absence(record)
        return BindingOutcome(absence=record)

    def trace_start(self, *, job_metadata: JobMetadata, working_memory: WorkingMemory, domain_code: str) -> str | None:
        """Open the binding's node in the execution graph, its input being the root's stuff, and return its id."""
        trace_context = job_metadata.trace_context
        if trace_context is None or not trace_context.emit_graph_events:
            return None
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None:
            return None
        root_stuff = working_memory.get_optional_stuff(self.root_name)
        input_specs = (
            [make_stuff_io_spec(name=self.root_name, stuff=root_stuff, include_data=trace_context.data_inclusion.stuff_json_content)]
            if root_stuff is not None
            else None
        )
        node_id, _ = tracer_manager.on_pipe_start(
            trace_context=trace_context,
            pipe_code=self.from_path,
            pipe_type=BINDING_NODE_PIPE_TYPE,
            node_kind=NodeKind.BINDING,
            started_at=datetime.now(UTC),
            input_specs=input_specs,
            description=f"Binds '{self.from_path}' to '{self.output_name}'",
            domain_code=domain_code,
        )
        execution_data: dict[str, Any] = {"from": self.from_path, "result": self.output_name}
        tracer_manager.register_execution_data(lookup_key=trace_context.lookup_key, node_id=node_id, execution_data=execution_data)
        return node_id

    def trace_end(self, *, job_metadata: JobMetadata, node_id: str | None, outcome: BindingOutcome) -> None:
        """Close the binding's node, registering it as the producer of the stuff it bound."""
        trace_context = job_metadata.trace_context
        if trace_context is None or node_id is None:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None:
            return
        output_spec = (
            make_stuff_io_spec(name=self.output_name, stuff=outcome.stuff, include_data=trace_context.data_inclusion.stuff_json_content)
            if outcome.stuff is not None
            else None
        )
        if outcome.is_skipped and outcome.absence is not None:
            tracer_manager.on_pipe_end_skipped(
                lookup_key=trace_context.lookup_key,
                node_id=node_id,
                ended_at=datetime.now(UTC),
                skip_reason=outcome.absence.reason,
                output_spec=output_spec,
            )
            return
        tracer_manager.on_pipe_end_success(
            lookup_key=trace_context.lookup_key,
            node_id=node_id,
            ended_at=datetime.now(UTC),
            output_spec=output_spec,
        )

    def trace_error(self, *, job_metadata: JobMetadata, node_id: str | None, error: BaseException | None) -> None:
        """Close the binding's node as failed, with the error that stopped it, whatever its class."""
        trace_context = job_metadata.trace_context
        if trace_context is None or node_id is None:
            return
        tracer_manager = GraphTracerManager.get_instance()
        if tracer_manager is None:
            return
        tracer_manager.on_pipe_end_error(
            lookup_key=trace_context.lookup_key,
            node_id=node_id,
            ended_at=datetime.now(UTC),
            error_type=type(error).__name__ if error is not None else "UnknownError",
            error_message=str(error) if error is not None else "the binding step stopped without binding a value",
        )
