"""Pin that a library's dynamically generated structure classes never escape into another library.

Concept materialization generates a structure class per class-backed concept and registers it under
a *name* key (``domain__Concept``). While a library carried no class registry of its own, every load
in the process resolved through to the one process-global registry, so two loads of the same concept
ref shared a single slot. Two contaminations followed, and both are reproduced here because both are
reachable from one process serving several bundles — the API's validate route, the hosted dry-validate
activity, every crate route:

- **Sequential reuse**, needing no concurrency at all: ``ConceptFactory`` reuses an already-registered
  class for a *basic* concept, so a later bundle declaring ``Summary`` with only a description inherited
  an earlier bundle's structured ``Summary`` — in its IO contracts and in the class its ``PipeLLM``
  would structure output against.
- **Concurrent overwrite**, needing a real suspension point inside the validate window: two loads
  generating the same ref overwrite each other's registration, and whichever landed last is what both
  render schemas from. A ``PipeParallel`` fan-out supplies the ``await`` (the dry-run sweep of a plain
  ``PipeLLM`` chain never yields).

Both are closed structurally by ``LibraryManager.open_library`` attaching a per-library ``ClassRegistry``
seeded from the process-global one, so these tests fail loudly if that ever regresses to opt-in.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, cast

import pytest
from kajson.kajson_manager import KajsonManager

from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager, set_current_library
from pipelex.pipeline.validate_bundle import validate_bundle
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.runtime_hub import get_class_registry

_STRUCTURED_SUMMARY_MTHDS = """
domain = "registry_isolation"
description = "Bundle whose Summary carries a private structure"

[concept.Summary]
description = "A structured summary"

[concept.Summary.structure]
first_tenant_field = { type = "text", description = "The first tenant's private field" }

[pipe.consume_summary]
type = "PipeLLM"
description = "Consume a summary"
inputs = { summary = "Summary" }
output = "Text"
prompt = "Summarize $summary"
"""

_BASIC_SUMMARY_MTHDS = """
domain = "registry_isolation"
description = "Bundle whose Summary is declared with a description only"

[concept.Summary]
description = "A plain summary"

[pipe.make_summary]
type = "PipeLLM"
description = "Make a summary"
inputs = { doc = "Text" }
output = "Summary"
prompt = "Summarize $doc"
"""


def _fan_out_mthds(*, field_name: str, tag: str) -> str:
    """A bundle whose dry-run sweep really yields: PipeParallel fans out through ``asyncio.gather``."""
    return f"""
domain = "registry_isolation"
description = "Fan-out bundle {tag}"

[concept.Summary]
description = "A summary ({tag})"

[concept.Summary.structure]
{field_name} = {{ type = "text", description = "The {tag} tenant's private field" }}

[pipe.branch_one_{tag}]
type = "PipeLLM"
description = "Branch one"
inputs = {{ summary = "Summary" }}
output = "Text"
prompt = "One: $summary"

[pipe.branch_two_{tag}]
type = "PipeLLM"
description = "Branch two"
inputs = {{ summary = "Summary" }}
output = "Text"
prompt = "Two: $summary"

[pipe.fan_{tag}]
type = "PipeParallel"
description = "Fan out over the summary"
inputs = {{ summary = "Summary" }}
output = "Composite"
add_each_output = true
branches = [
  {{ pipe = "branch_one_{tag}", result = "one" }},
  {{ pipe = "branch_two_{tag}", result = "two" }},
]
"""


def _schema_property_names(json_schema: dict[str, Any]) -> list[str]:
    """The sorted field names of a structure class's JSON Schema, as the IO contract carries it."""
    properties = cast("dict[str, Any]", json_schema.get("properties") or {})
    return sorted(properties)


def _teardown_validation_library() -> None:
    """Tear down the library ``validate_bundle`` leaves open on success."""
    validation_library_id = get_current_library_id_or_none()
    clear_current_library()
    if validation_library_id is not None:
        get_library_manager().teardown(library_id=validation_library_id)


class TestLibraryClassRegistryIsolation:
    @pytest.mark.asyncio(loop_scope="class")
    async def test_a_basic_concept_does_not_inherit_an_earlier_bundles_structure_class(self) -> None:
        """A later basic ``Summary`` must not reuse an earlier bundle's structured ``Summary`` class."""
        first_report = await validate_bundles_in_process(mthds_contents=[_STRUCTURED_SUMMARY_MTHDS])
        first_schema = first_report.pipe_io_contracts["registry_isolation.consume_summary"].inputs["summary"].json_schema
        assert _schema_property_names(first_schema) == ["first_tenant_field"]

        second_report = await validate_bundles_in_process(mthds_contents=[_BASIC_SUMMARY_MTHDS])
        second_dump = json.dumps(second_report.input_form["registry_isolation.make_summary"].model_dump(mode="json"))
        assert "first_tenant_field" not in second_dump

        # The class the second bundle's PipeLLM would structure its output against, read inside the
        # second bundle's own library window (validate_bundle leaves the library open on success).
        await validate_bundle(mthds_contents=[_BASIC_SUMMARY_MTHDS])
        try:
            structure_class = get_class_registry().get_required_subclass(
                name="registry_isolation__Summary",
                base_class=StuffContent,
            )
            assert "first_tenant_field" not in structure_class.model_fields
        finally:
            _teardown_validation_library()

        # And nothing from either bundle was left behind in the process-global registry.
        assert not KajsonManager.get_class_registry().has_class(name="registry_isolation__Summary")

    @pytest.mark.asyncio(loop_scope="class")
    async def test_concurrent_validates_do_not_overwrite_each_others_structure_class(self) -> None:
        """Two validates yielding inside their windows must each keep their own generated class."""
        first_report, second_report = await asyncio.gather(
            validate_bundles_in_process(mthds_contents=[_fan_out_mthds(field_name="alpha_field", tag="alpha")]),
            validate_bundles_in_process(mthds_contents=[_fan_out_mthds(field_name="gamma_field", tag="gamma")]),
        )

        first_schema = first_report.pipe_io_contracts["registry_isolation.fan_alpha"].inputs["summary"].json_schema
        second_schema = second_report.pipe_io_contracts["registry_isolation.fan_gamma"].inputs["summary"].json_schema
        assert _schema_property_names(first_schema) == ["alpha_field"]
        assert _schema_property_names(second_schema) == ["gamma_field"]

    @pytest.mark.asyncio(loop_scope="class")
    async def test_an_opened_library_carries_its_own_registry_seeded_from_the_global_one(self) -> None:
        """The structural invariant behind both tests above, asserted directly."""
        library_manager = get_library_manager()
        library_id, library = library_manager.open_library()
        global_registry = KajsonManager.get_class_registry()

        library_registry = library.get_class_registry()
        assert library_registry is not None
        assert library_registry is not global_registry
        assert set(global_registry.get_classes_dict()) <= set(library_registry.get_classes_dict())

        set_current_library(library_id=library_id)
        try:
            assert get_class_registry() is library_registry
        finally:
            clear_current_library()
            library_manager.teardown(library_id=library_id)
