"""Pin the real reload behind ``--save-csv`` on a run that produced no rows.

The run's own library — and the ``ClassRegistry`` holding the structure classes its bundle
generated — is torn down before the CSV step runs, and an empty result leaves no instance to read
the row class off. The CLI therefore reloads the same bundle into a throwaway library just long
enough to resolve the declared concept's structure class, which is what keeps a zero-row run writing
a correct header-only file. Exercised here against a real load rather than a mock, so a class that
the reload cannot actually regenerate fails the test.
"""

from __future__ import annotations

import pytest

from pipelex.cli.commands.run._run_core import _resolve_row_model_for_empty_result  # pyright: ignore[reportPrivateUsage]
from pipelex.interpreter_hub import clear_current_library, get_concept_library, get_library_manager
from pipelex.pipeline.execution_seams import acquire_library
from pipelex.tools.tabular.csv_codec import flat_field_names

_FLAT_ROW_MTHDS = """
domain = "csv_empty_result"
description = "Bundle whose row concept is generated from a structure table"

[concept.PersonSummary]
description = "A flat person summary"

[concept.PersonSummary.structure]
name = { type = "text", description = "The person's name" }
country = { type = "text", description = "The person's country" }

[pipe.summarize_people]
type = "PipeLLM"
description = "Summarize people"
inputs = { doc = "Text" }
output = "PersonSummary[]"
prompt = "Summarize $doc"
"""


@pytest.mark.asyncio(loop_scope="class")
class TestSaveCsvEmptyResultRowModel:
    async def test_the_reload_resolves_a_generated_structure_class(self) -> None:
        # Load once to obtain the concept the run's output stuff would carry, then drop that library
        # entirely — standing in for the run library the runner tears down before the CSV step.
        library_id, _main_pipe = acquire_library(library_id="", mthds_contents=[_FLAT_ROW_MTHDS])
        try:
            row_concept = get_concept_library().get_required_concept(concept_ref="csv_empty_result.PersonSummary")
        finally:
            clear_current_library()
            get_library_manager().teardown(library_id=library_id)

        row_model = _resolve_row_model_for_empty_result(
            concept=row_concept,
            bundle_path=None,
            mthds_content=_FLAT_ROW_MTHDS,
            library_dir=None,
        )

        assert flat_field_names(row_model) == ["name", "country"], "The header a zero-row CSV would carry"
