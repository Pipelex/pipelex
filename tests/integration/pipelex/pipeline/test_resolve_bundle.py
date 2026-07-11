"""Integration: ``resolve_crate_from_contents`` — the in-memory (host-facing) resolve core.

Pins the contract the HTTP resolve/codegen routes build on: in-memory contents resolve to a
normalized crate through the same engine as the CLI, an invalid library raises the one shared
``ValidateBundleError``, and the library lifecycle honors the loaded-on-success /
torn-down-on-failure contract of ``validate_bundle``.
"""

from collections.abc import Callable

import pytest
from mthds.package.manifest.schema import MTHDS_STANDARD_VERSION
from pytest_mock import MockerFixture

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.pipeline.exceptions import ValidateBundleError
from pipelex.pipeline.resolve_bundle import resolve_crate_from_contents

MAIN_MTHDS = """\
domain = "pipeline"
description = "Pipeline domain"

[concept.Report]
description = "A report"
structure.score = { description = "the score", type = "concept", concept_ref = "Score" }
structure.label = { description = "a label", type = "concept", concept_ref = "Text" }

[pipe.run_pipeline]
type = "PipeSequence"
description = "Run the pipeline"
inputs = { doc = "Text" }
output = "Score"
steps = [{ pipe = "compute_score", result = "score" }]
"""

STEPS_MTHDS = """\
domain = "pipeline"

[concept.Score]
description = "A score"
structure = { value = { description = "the value", type = "number" } }

[pipe.compute_score]
type = "PipeLLM"
description = "Compute a score"
inputs = { doc = "Text" }
output = "Score"
model = "$quick-reasoning"
prompt = "Compute a score from $doc"
"""

# The pipe references a concept that no bundle declares — a load-stage library error, translated
# by the shared cascade into a ValidateBundleError carrying structured validation errors.
INVALID_MTHDS = """\
domain = "broken"
description = "Broken domain"

[pipe.bad_pipe]
type = "PipeLLM"
description = "References an undeclared concept"
inputs = { doc = "NoSuchConcept" }
output = "Text"
prompt = "Do something with $doc"
"""

ADDRESS_DEPENDENCY_MTHDS = """\
domain = "host"

[pipe.run_host]
type = "PipeSequence"
description = "Run an installed dependency"
inputs = { doc = "Text" }
output = "Text"
steps = [{ pipe = "github.com/org/pkg->remote.process", result = "result" }]
"""


class TestResolveCrateFromContents:
    def test_multi_bundle_contents_resolve_to_normalized_crate(self, load_empty_library: Callable[[], str]):
        """A multi-bundle in-memory closure resolves to a flat, fully-qualified, natives-materialized crate,
        and the library is left loaded + current for the host (which then owns teardown).
        """
        load_empty_library()
        library_manager = get_library_manager()
        crate = resolve_crate_from_contents(
            mthds_contents=[MAIN_MTHDS, STEPS_MTHDS],
            mthds_sources=["main.mthds", "steps.mthds"],
        )
        library_id = get_current_library_id_or_none()
        try:
            assert crate.fingerprint
            assert crate.mthds_version == MTHDS_STANDARD_VERSION
            assert "pipeline.Report" in crate.concepts
            assert "pipeline.Score" in crate.concepts
            assert "native.Text" in crate.concepts, "referenced natives must be materialized into the normalized crate"
            assert "pipeline.run_pipeline" in crate.pipes
            assert "pipeline.compute_score" in crate.pipes
            # Sources threaded onto the blueprints surface in the crate's provenance map.
            assert crate.source_map.get("pipeline.run_pipeline") == "main.mthds"
            assert crate.source_map.get("pipeline.compute_score") == "steps.mthds"
            # Loaded-on-success: the freshly opened library is current, so the host can read live pipes.
            assert library_id is not None
        finally:
            clear_current_library()
            if library_id is not None:
                library_manager.teardown(library_id=library_id)

    def test_invalid_contents_raise_shared_verdict_and_tear_down(self, load_empty_library: Callable[[], str], mocker: MockerFixture):
        """An invalid library raises the one shared ValidateBundleError (structured items present),
        the opened library is torn down, and the caller's current-library state is restored.
        """
        load_empty_library()
        library_manager = get_library_manager()
        open_library_spy = mocker.spy(library_manager, "open_library")
        teardown_spy = mocker.spy(library_manager, "teardown")
        current_before = get_current_library_id_or_none()

        teardown_calls_before = teardown_spy.call_count
        with pytest.raises(ValidateBundleError) as exc_info:
            resolve_crate_from_contents(mthds_contents=[INVALID_MTHDS], mthds_sources=["broken.mthds"])

        error_report = exc_info.value.to_error_report()
        assert error_report.validation_errors, "the shared builder must produce structured validation-error items"

        assert teardown_spy.call_count == teardown_calls_before + 1
        opened_library_id, _ = open_library_spy.spy_return
        assert teardown_spy.call_args_list[-1].kwargs["library_id"] == opened_library_id
        assert get_current_library_id_or_none() == current_before

    def test_empty_contents_are_a_host_wiring_error(self):
        with pytest.raises(PipelexUnexpectedError):
            resolve_crate_from_contents(mthds_contents=[])

    def test_sources_length_mismatch_is_a_host_wiring_error(self):
        with pytest.raises(PipelexUnexpectedError):
            resolve_crate_from_contents(mthds_contents=[MAIN_MTHDS], mthds_sources=["a.mthds", "b.mthds"])

    def test_address_dependency_is_rejected_without_filesystem_discovery(self, load_empty_library: Callable[[], str], mocker: MockerFixture) -> None:
        load_empty_library()
        discovery = mocker.patch(
            "pipelex.libraries.library_manager.find_method_by_full_address",
            side_effect=AssertionError("in-memory resolve must not discover installed methods"),
        )

        with pytest.raises(ValidateBundleError, match="address-based dependency"):
            resolve_crate_from_contents(mthds_contents=[ADDRESS_DEPENDENCY_MTHDS], mthds_sources=["host.mthds"])

        discovery.assert_not_called()
