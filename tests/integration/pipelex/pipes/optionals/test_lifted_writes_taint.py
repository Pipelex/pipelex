"""A pipe that may be lifted still stores what its runs store, and the absence analyses must join both.

A condition's chosen outcome runs on its caller's memory, and an outcome may be lifted for an optional input of the condition
it takes plain: the lift then resolves the condition's result, and every name the outcome always stores, to an absence. A
sequence step that may be lifted may also run, and a run that stores a name may leave it absent. Each bundle here validated
once while its run resolved an output declared plain to an absence; each must now be refused, or, declared optional, run as
the analysis says.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest

from pipelex.core.memory.absence import AbsenceKind, AbsenceRecord
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.condition.pipe_condition import PipeCondition
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.controller_taint import collect_controller_taint_analyses
from pipelex.pipeline.liftable_pipes import build_liftable_pipes
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

_LIFTED_OUTCOME_DOMAIN = "probe_cond_lift"


def _lifted_outcome_bundle(*, pick_output: str, outer_output: str) -> str:
    """A condition taking `doc` optional routes to `inner`, which takes it plain, and the caller binds what `inner` stores."""
    return f"""domain = "{_LIFTED_OUTCOME_DOMAIN}"
description = "A condition outcome skipped for an absent input"
main_pipe = "outer"

[concept.Doc]
description = "A document"

[concept.Doc.structure]
label = {{ type = "text", description = "Its label", required = true }}

[pipe.outer]
type = "PipeSequence"
description = "Route, then bind what the outcome stored"
inputs = {{ doc = "Doc?", mode = "Text" }}
output = "{outer_output}"
steps = [
  {{ pipe = "pick", result = "picked" }},
  {{ from = "label", result = "final" }},
]

[pipe.pick]
type            = "PipeCondition"
description     = "Route by mode"
inputs          = {{ mode = "Text", doc = "Doc?" }}
output          = "{pick_output}"
expression      = "mode"
default_outcome = "inner"

[pipe.pick.outcomes]
other = "inner"

[pipe.inner]
type = "PipeSequence"
description = "Bind the label"
inputs = {{ doc = "Doc" }}
output = "Text"
steps = [
  {{ from = "doc.label", result = "label" }},
]
"""


_SOMETIMES_WRITTEN_DOMAIN = "probe_sometimes"


def _sometimes_written_bundle(*, outer_output: str) -> str:
    """A step that may be lifted for an absent `doc` runs a condition that, on some runs, stores `x` from a path that may find nothing."""
    return f"""domain = "{_SOMETIMES_WRITTEN_DOMAIN}"
description = "A liftable step that stores a name on some runs only"
main_pipe = "outer"

[concept.Doc]
description = "A document"

[concept.Doc.structure]
label = {{ type = "text", description = "Its label", required = true }}
note = {{ type = "text", description = "Its note" }}

[pipe.outer]
type = "PipeSequence"
description = "Seed x, maybe overwrite it, then bind it"
inputs = {{ doc = "Doc?", mode = "Text", seed = "Text" }}
output = "{outer_output}"
steps = [
  {{ from = "seed", result = "x" }},
  {{ pipe = "pick", result = "picked" }},
  {{ from = "x", result = "final" }},
]

[pipe.pick]
type            = "PipeCondition"
description     = "Route by mode"
inputs          = {{ mode = "Text", doc = "Doc" }}
output          = "Text?"
expression      = "mode"
default_outcome = "continue"

[pipe.pick.outcomes]
a = "store_note"

[pipe.store_note]
type = "PipeSequence"
description = "Bind the note as x"
inputs = {{ doc = "Doc" }}
output = "Text?"
steps = [
  {{ from = "doc.note", result = "x" }},
]
"""


_GUARDED_DOMAIN = "probe_guarded"


def _guarded_bundle(*, flag_spec: str) -> str:
    """A condition chooses `flagged_note`, which takes `flag` as `flag_spec`, only when its optional `flag` is present."""
    return f"""domain = "{_GUARDED_DOMAIN}"
description = "A condition whose expression guards an optional input"
main_pipe = "route"

[pipe.route]
type                = "PipeCondition"
description         = "Route on the presence of the flag"
inputs              = {{ flag = "Text?" }}
output              = "Text"
expression_template = "{{{{ 'with_flag' if flag is defined else 'no_flag' }}}}"
default_outcome     = "plain_note"

[pipe.route.outcomes]
with_flag = "flagged_note"
no_flag   = "plain_note"

[pipe.flagged_note]
type        = "PipeCompose"
description = "Note the flag"
inputs      = {{ flag = "{flag_spec}" }}
output      = "Text"
template    = "Flagged: {{{{ flag }}}}"

[pipe.plain_note]
type        = "PipeCompose"
description = "Note that there is no flag"
output      = "Text"
template    = "Plain"
"""


def _text_input(text: str) -> dict[str, Any]:
    return {"concept": "native.Text", "content": {"text": text}}


def _doc_input(*, domain: str, content: dict[str, str]) -> dict[str, Any]:
    return {"concept": f"{domain}.Doc", "content": content}


def _load_pipes(*, mthds_content: str, library_id: str) -> dict[str, PipeAbstract]:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="probe.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    return {pipe.code: pipe for pipe in pipes}


async def _run(*, mthds_content: str, inputs: "PipelineInputs") -> AbsenceRecord | str:
    """Run the bundle live, and return the text it output, or the absence its output holds."""
    response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(mthds_contents=[mthds_content], inputs=inputs)
    main_resolved = response.pipe_output.working_memory.resolve_main_stuff()
    if isinstance(main_resolved, AbsenceRecord):
        return main_resolved
    return response.pipe_output.main_stuff_as_str


class TestLiftedWritesTaint:
    def test_a_condition_that_may_lift_its_outcome_declares_its_output_optional(self, load_empty_library: Callable[[], str]) -> None:
        """Regression: `pick` takes `doc` optional and routes to `inner`, which takes it plain, so a run without `doc` lifts
        `inner` and resolves the condition's result to an absence: a plain output would hide it.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            _load_pipes(mthds_content=_lifted_outcome_bundle(pick_output="Text", outer_output="Text?"), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert exc_info.value.pipe_code == "pick"
        assert "'inner'" in str(exc_info.value)
        assert "'doc'" in str(exc_info.value)

    def test_a_name_a_liftable_outcome_always_stores_may_be_absent(self, load_empty_library: Callable[[], str]) -> None:
        """Regression: the lift of `inner` resolves `label`, which it always stores, to an absence, so `final`, bound from it,
        may be absent, and `outer` must declare its output optional.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            _load_pipes(mthds_content=_lifted_outcome_bundle(pick_output="Text?", outer_output="Text"), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert exc_info.value.pipe_code == "outer"
        assert "pipe 'inner' may be skipped when 'doc' is absent → slot 'label'" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_lifted_outcome_resolves_what_the_analysis_says(self, load_empty_library: Callable[[], str]) -> None:
        mthds_content = _lifted_outcome_bundle(pick_output="Text?", outer_output="Text?")
        pipes = _load_pipes(mthds_content=mthds_content, library_id=load_empty_library())

        pick = pipes["pick"]
        assert isinstance(pick, PipeCondition)
        label_write = pick.memory_writes()["label"]
        assert label_write.is_always_written
        assert label_write.absence is not None
        assert label_write.absence.origin_slot_name == "doc"
        inventory = build_liftable_pipes(collect_controller_taint_analyses(list(pipes.values())))
        assert [(entry.within_pipe_ref, entry.pipe_ref, entry.skipped_when_absent) for entry in inventory] == [
            (f"{_LIFTED_OUTCOME_DOMAIN}.pick", f"{_LIFTED_OUTCOME_DOMAIN}.inner", ["doc"])
        ]

        outcome = await _run(mthds_content=mthds_content, inputs={"mode": _text_input("x")})
        assert isinstance(outcome, AbsenceRecord)
        assert outcome.kind == AbsenceKind.SKIPPED
        assert outcome.upstream is not None
        assert outcome.upstream.variable_name == "label"
        outcome = await _run(
            mthds_content=mthds_content,
            inputs={"mode": _text_input("x"), "doc": _doc_input(domain=_LIFTED_OUTCOME_DOMAIN, content={"label": "L"})},
        )
        assert outcome == "L"

    def test_a_liftable_step_keeps_the_taint_of_what_its_run_may_store(self, load_empty_library: Callable[[], str]) -> None:
        """Regression: `pick` may be lifted for an absent `doc`, which leaves `x` as seeded, but it may also run, and its
        outcome may store `x` as an absence, so `final`, bound from `x`, may be absent.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            _load_pipes(mthds_content=_sometimes_written_bundle(outer_output="Text"), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert exc_info.value.pipe_code == "outer"
        assert "'doc.note'" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_liftable_step_resolves_what_the_analysis_says(self, load_empty_library: Callable[[], str]) -> None:
        mthds_content = _sometimes_written_bundle(outer_output="Text?")
        _load_pipes(mthds_content=mthds_content, library_id=load_empty_library())

        def inputs(*, mode: str, doc: dict[str, str] | None) -> "PipelineInputs":
            run_inputs: dict[str, Any] = {"mode": _text_input(mode), "seed": _text_input("s")}
            if doc is not None:
                run_inputs["doc"] = _doc_input(domain=_SOMETIMES_WRITTEN_DOMAIN, content=doc)
            return run_inputs

        outcome = await _run(mthds_content=mthds_content, inputs=inputs(mode="a", doc={"label": "L"}))
        assert isinstance(outcome, AbsenceRecord)
        assert await _run(mthds_content=mthds_content, inputs=inputs(mode="a", doc={"label": "L", "note": "N"})) == "N"
        assert await _run(mthds_content=mthds_content, inputs=inputs(mode="a", doc=None)) == "s"
        assert await _run(mthds_content=mthds_content, inputs=inputs(mode="b", doc={"label": "L"})) == "s"

    def test_a_guarded_outcome_taking_the_input_plain_is_refused(self, load_empty_library: Callable[[], str]) -> None:
        """Validation does not read the expression, so an outcome the guard chooses only with `flag` present, taking it plain,
        may be lifted as far as it can tell, and the refusal names the remedy that keeps the output plain.
        """
        with pytest.raises(PipeValidationError) as exc_info:
            _load_pipes(mthds_content=_guarded_bundle(flag_spec="Text"), library_id=load_empty_library())

        assert exc_info.value.error_type == PipeValidationErrorType.OPTIONAL_NOT_HANDLED
        assert exc_info.value.pipe_code == "route"
        assert "declare 'flag' forced on 'flagged_note' with '!'" in str(exc_info.value)

    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_guarded_outcome_forcing_the_input_keeps_the_output_plain(self, load_empty_library: Callable[[], str]) -> None:
        mthds_content = _guarded_bundle(flag_spec="Text!")
        pipes = _load_pipes(mthds_content=mthds_content, library_id=load_empty_library())

        assert build_liftable_pipes(collect_controller_taint_analyses(list(pipes.values()))) == []
        assert await _run(mthds_content=mthds_content, inputs={"flag": _text_input("urgent")}) == "Flagged: urgent"
        assert await _run(mthds_content=mthds_content, inputs={}) == "Plain"
