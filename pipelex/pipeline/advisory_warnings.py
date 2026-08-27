"""The one composition point for the validation report's advisory `warnings`.

A warning is a finding worth surfacing on a VALID bundle that must never flip `is_valid`. There are
three families of them today, each derived from a different substrate:

- **`optionality`** — the useless-`!` lint, from the controllers' taint analyses.
- **`presence vacuity`** — the entry-pipe lint, from the input-form descriptors.
- **`hints`** — the intent-hints lints, from the qualified crate.

They used to be assembled site by site, and the sites disagreed: the protocol path carried the
optionality and hint lints, while the agent CLI, the builder ops and the bare CLI each carried the
optionality lint alone — so which advisories an author saw depended on which command they typed.
This module removes that: one function builds every family in one fixed order, and every channel
calls it. There is deliberately no flag selecting which families a channel carries, because such a
flag would preserve exactly the disagreement this module exists to remove.

Two entry points, because the channels hold different things in hand:

- :func:`build_advisory_warnings` is pure over precomputed ingredients, for a caller that already
  built them for other reasons (the protocol path needs `input_form` for the report anyway).
- :func:`collect_advisory_warnings` gathers the ingredients itself, for a caller that holds only
  the loaded pipes.

Both must run **inside the open validation window**: the descriptors' class-backed reflection reads
the class registry, and the crate is read off the current library.
"""

from collections.abc import Iterable, Sequence

from pipelex.base_exceptions import ValidationErrorItem
from pipelex.interpreter_hub import get_current_library, get_library_manager
from pipelex.libraries.crate_qualification import QualifiedCrateContent
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipeline.blueprint_selection import collect_entry_pipe_refs
from pipelex.pipeline.controller_taint import ControllerTaintAnalysis, collect_controller_taint_analyses
from pipelex.pipeline.hint_warnings import build_hint_warnings
from pipelex.pipeline.input_form import InputForm, build_input_form, qualify_current_library_crate
from pipelex.pipeline.optionality_warnings import build_optionality_warnings
from pipelex.pipeline.vacuous_presence_warnings import build_vacuous_presence_warnings


def build_advisory_warnings(
    *,
    taint_analyses: Sequence[ControllerTaintAnalysis],
    input_form: InputForm,
    entry_pipe_refs: Iterable[str],
    qualified_crate: QualifiedCrateContent,
) -> list[ValidationErrorItem]:
    """Every advisory family, concatenated in one fixed order.

    Pure: it derives nothing itself, so a caller that already built these artifacts pays for them
    once. Each family is internally deterministic, and the family order is fixed here rather than
    per channel — a consumer reading `warnings` sees the same sequence whichever command produced it.

    Args:
        taint_analyses: The controllers' analyses (`collect_controller_taint_analyses`).
        input_form: The batch's input-form descriptors (`build_input_form`).
        entry_pipe_refs: The qualified refs of the batch's entry pipes (`collect_entry_pipe_refs`).
        qualified_crate: The current library's qualified crate (`qualify_current_library_crate`).

    Returns:
        The advisory items: optionality, then presence vacuity, then hints.
    """
    return [
        *build_optionality_warnings(taint_analyses),
        *build_vacuous_presence_warnings(input_form=input_form, entry_pipe_refs=entry_pipe_refs),
        *build_hint_warnings(qualified_crate),
    ]


def collect_advisory_warnings(*, pipes: Sequence[PipeAbstract], entry_pipe_refs: Iterable[str]) -> list[ValidationErrorItem]:
    """Gather every advisory ingredient inside the validation window, then build the warnings.

    The crate is qualified ONCE here and handed to both consumers that need it — the descriptors and
    the hint lint — rather than each qualifying the accumulated crate for itself.

    Args:
        pipes: The loaded pipes to judge (typically `ValidateBundleResult.pipes`, or every pipe of
            the current library on the library-wide path).
        entry_pipe_refs: The qualified refs of the batch's entry pipes (`collect_entry_pipe_refs`).

    Returns:
        The advisory items, in the order :func:`build_advisory_warnings` fixes.
    """
    qualified_crate = qualify_current_library_crate()
    return build_advisory_warnings(
        taint_analyses=collect_controller_taint_analyses(pipes),
        input_form=build_input_form(pipes, qualified_crate=qualified_crate),
        entry_pipe_refs=entry_pipe_refs,
        qualified_crate=qualified_crate,
    )


def collect_current_library_entry_pipe_refs() -> list[str]:
    """The entry pipe refs of every bundle accumulated into the current library.

    What the library-wide channels use: `validate all` holds no `ValidateBundleResult`, so the
    declared `main_pipe`s come off the blueprints the library manager retained on the way in.
    Returns nothing for a library loaded straight from a transported crate, which accumulates no
    blueprints — the same silence as a batch that declares no `main_pipe`.

    A dependency package's own `main_pipe` is deliberately NOT an entry ref here. Only the bundles
    the author is validating are accumulated onto the library; a dependency's blueprints load into
    an isolated child library instead, so its `main_pipe` never reaches this list. That is the
    scoping the entry-pipe lints want on both counts: the remedies they state (mark the input
    optional, give the concept a required field) are edits to a package the author does not own,
    and a dependency's concepts never enter this library's crate anyway — every slot of a
    dependency pipe derives an `unknown` node, which those lints skip. Including the refs would
    add findings nobody can act on, or no findings at all.
    """
    return collect_entry_pipe_refs(get_library_manager().get_accumulated_blueprints(get_current_library()))
