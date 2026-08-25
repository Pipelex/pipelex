"""The vacuous-presence lint on the protocol `validate` path, over real bundles.

The unit decision table (`tests/unit/pipelex/pipeline/test_vacuous_presence_warnings.py`) pins the
rule over hand-built descriptors. These pin the half the unit table cannot see: that a bundle an
author actually writes derives the descriptor the lint fires on, that the entry-pipe scope really
does follow the declared `main_pipe`, and that a warning never touches the verdict.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import Field

from pipelex.core.stuffs.structured_content import StructuredContent
from pipelex.interpreter_hub import clear_current_library
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.system.registries.class_registry_access import get_class_registry
from pipelex.validation_error_types import HintLintErrorType, PipeValidationErrorType

if TYPE_CHECKING:
    from collections.abc import Callable

    from pipelex.base_exceptions import ValidationErrorItem

_ENTRY_PIPE_MTHDS = """
domain = "vacuous_entry"
description = "Entry pipe demanding an all-optional structure, with a sibling that does the same"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }
depth = { type = "integer", description = "How deep to go" }

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"

[pipe.helper]
type = "PipeLLM"
description = "A sibling with the very same input shape, reached by nothing"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Help with $opts"
"""

_OPTIONAL_SLOT_MTHDS = """
domain = "vacuous_optional"
description = "The same shape with the slot marked optional"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }

[pipe.run]
type = "PipeLLM"
description = "The entry pipe, tolerating an absent slot"
inputs = { opts = "RunOptions?" }
output = "Text"
prompt = "Run{% if opts %} with $opts{% endif %}"
"""

_REQUIRED_FIELD_MTHDS = """
domain = "vacuous_required"
description = "The same shape with one required field"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use", required = true }
depth = { type = "integer", description = "How deep to go" }

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"
"""

_NO_MAIN_PIPE_MTHDS = """
domain = "vacuous_no_main"
description = "The warnable shape in a bundle that declares no main_pipe"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }

[pipe.run]
type = "PipeLLM"
description = "A pipe no bundle declares as its entry point"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"
"""

_EMPTY_STRUCTURE_MTHDS = """
domain = "vacuous_empty"
description = "Entry pipe demanding a concept whose authored structure table holds no field"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"

[concept.RunOptions.structure]

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"
"""

_CLASS_BACKED_MTHDS = """
domain = "vacuous_class"
description = "Entry pipe demanding a class-backed concept whose fields all carry defaults"
main_pipe = "run"

[concept.Settings]
description = "Settings backed by a hand-written class"
structure = "VacuousAllDefaultedPayload"

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { settings = "Settings" }
output = "Text"
prompt = "Run with $settings"
"""

_FIELD_LESS_CLASS_MTHDS = """
domain = "vacuous_field_less"
description = "Entry pipe demanding a class-backed concept whose class declares no field"
main_pipe = "run"

[concept.Settings]
description = "Settings backed by a class with no field"
structure = "VacuousFieldLessPayload"

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { settings = "Settings" }
output = "Text"
prompt = "Run with $settings"
"""

_HINTED_MTHDS = """
domain = "vacuous_hinted"
description = "The warnable shape beside a warnable hint"
main_pipe = "run"

[concept.RunOptions]
description = "Options for the run"
hints = { emphasis = "strong" }

[concept.RunOptions.structure]
tone = { type = "text", description = "The tone to use" }

[pipe.run]
type = "PipeLLM"
description = "The entry pipe"
inputs = { opts = "RunOptions" }
output = "Text"
prompt = "Run with $opts"
"""


class VacuousAllDefaultedPayload(StructuredContent):
    """A hand-written structure class whose every field carries a default — all-optional by reflection."""

    tone: str = Field(default="neutral", description="The tone to use")
    depth: int | None = Field(default=None, description="How deep to go")


class VacuousFieldLessPayload(StructuredContent):
    """A hand-written structure class declaring no field at all — an empty object is all that fits it."""


def _vacuous(warnings: list[ValidationErrorItem]) -> list[ValidationErrorItem]:
    return [warning for warning in warnings if warning.error_type == PipeValidationErrorType.INPUT_PRESENCE_VACUOUS]


@pytest.mark.asyncio(loop_scope="class")
class TestVacuousPresenceLint:
    async def _warnings(self, *, mthds: str, load_empty_library: Callable[[], str]) -> list[ValidationErrorItem]:
        load_empty_library()
        try:
            report = await PipelexMTHDSProtocol().validate(mthds_contents=[mthds])
            assert report.is_runnable is True, "An advisory warning must never touch the verdict"
            return report.warnings
        finally:
            clear_current_library()

    async def test_entry_pipe_warns_and_the_report_stays_valid_and_runnable(self, load_empty_library: Callable[[], str]) -> None:
        warnings = await self._warnings(mthds=_ENTRY_PIPE_MTHDS, load_empty_library=load_empty_library)

        vacuous = _vacuous(warnings)
        assert len(vacuous) == 1, "Only the declared main_pipe is linted, not its identically-shaped sibling"
        assert vacuous[0].pipe_code == "run"
        assert vacuous[0].domain_code == "vacuous_entry"
        assert vacuous[0].variable_names == ["opts"]
        assert "vacuous_entry.RunOptions" in vacuous[0].message

    async def test_the_same_shape_on_a_non_entry_pipe_is_silent(self, load_empty_library: Callable[[], str]) -> None:
        """`helper` declares the very same input as `run`, in the same bundle. Only `run` is warned about."""
        warnings = await self._warnings(mthds=_ENTRY_PIPE_MTHDS, load_empty_library=load_empty_library)

        assert [warning.pipe_code for warning in _vacuous(warnings)] == ["run"]

    async def test_an_optional_slot_is_silent(self, load_empty_library: Callable[[], str]) -> None:
        warnings = await self._warnings(mthds=_OPTIONAL_SLOT_MTHDS, load_empty_library=load_empty_library)

        assert _vacuous(warnings) == []

    async def test_one_required_field_silences_the_lint(self, load_empty_library: Callable[[], str]) -> None:
        warnings = await self._warnings(mthds=_REQUIRED_FIELD_MTHDS, load_empty_library=load_empty_library)

        assert _vacuous(warnings) == []

    async def test_a_bundle_with_no_main_pipe_is_not_linted(self, load_empty_library: Callable[[], str]) -> None:
        warnings = await self._warnings(mthds=_NO_MAIN_PIPE_MTHDS, load_empty_library=load_empty_library)

        assert _vacuous(warnings) == []

    async def test_an_empty_structure_table_warns_with_the_field_less_wording(self, load_empty_library: Callable[[], str]) -> None:
        """The design's second row: a concept declaring no field at all, which only an empty object fits.

        It is reachable because the deriver branches on `structure is not None` the way `ConceptFactory`
        does — the truthiness test it used to run reported such a concept as `prose`, which this lint
        never looks at, so the wording below was unreachable from any bundle an author can write.
        """
        warnings = await self._warnings(mthds=_EMPTY_STRUCTURE_MTHDS, load_empty_library=load_empty_library)

        vacuous = _vacuous(warnings)
        assert len(vacuous) == 1
        assert vacuous[0].variable_names == ["opts"]
        assert "declares no field at all" in vacuous[0].message
        assert "give 'vacuous_empty.RunOptions' a required field" in vacuous[0].message

    async def test_a_class_backed_concept_with_all_defaulted_fields_warns(self, load_empty_library: Callable[[], str]) -> None:
        """The lint reads the descriptor, so class-backed reflection is covered for free: a pydantic
        class whose every field carries a default demands nothing, exactly as an all-optional
        authored structure does.
        """
        get_class_registry().register_class(VacuousAllDefaultedPayload)
        warnings = await self._warnings(mthds=_CLASS_BACKED_MTHDS, load_empty_library=load_empty_library)

        vacuous = _vacuous(warnings)
        assert len(vacuous) == 1
        assert vacuous[0].variable_names == ["settings"]
        assert "vacuous_class.Settings" in vacuous[0].message

    async def test_a_field_less_class_backed_concept_warns_with_the_field_less_wording(self, load_empty_library: Callable[[], str]) -> None:
        """A registered class declaring no field demands nothing, exactly as an empty structure table does.

        The descriptor used to call such a concept `unknown` — the kind reserved for a payload it
        genuinely cannot read — which the object-only guard then silenced. Zero fields is a reading,
        not a failure to read, so the form says `object` and the lint has something honest to say.
        """
        get_class_registry().register_class(VacuousFieldLessPayload)
        warnings = await self._warnings(mthds=_FIELD_LESS_CLASS_MTHDS, load_empty_library=load_empty_library)

        vacuous = _vacuous(warnings)
        assert len(vacuous) == 1
        assert vacuous[0].variable_names == ["settings"]
        assert "declares no field at all" in vacuous[0].message
        assert "give 'vacuous_field_less.Settings' a required field" in vacuous[0].message

    async def test_the_hint_lint_still_rides_beside_it(self, load_empty_library: Callable[[], str]) -> None:
        warnings = await self._warnings(mthds=_HINTED_MTHDS, load_empty_library=load_empty_library)

        assert [warning.error_type for warning in warnings] == [
            PipeValidationErrorType.INPUT_PRESENCE_VACUOUS,
            HintLintErrorType.HINT_UNKNOWN_KEY,
        ]
