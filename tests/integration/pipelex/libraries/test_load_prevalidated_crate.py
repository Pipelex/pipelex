import pytest
from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.interpreter_hub import clear_current_library, get_library_manager, get_required_pipe, set_current_library
from pipelex.libraries.library import Library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.system.pipe_run_mode import PipeRunMode

PREVALIDATED_MTHDS = """\
domain = "prevalidated"
description = "A crate loaded with and without re-validation"
main_pipe = "main"

[concept.Idea]
description = "An idea"

[concept.Idea.structure]
title = { type = "text", description = "The title", required = true }
score = { type = "integer", description = "The score", required = true }

[concept.Verdict]
description = "A verdict on an idea"

[concept.Verdict.structure]
summary = { type = "text", description = "The summary", required = true }
flag = { type = "boolean", description = "The flag", required = true }

[pipe.invent_idea]
type = "PipeLLM"
description = "Invent an idea"
output = "Idea"
model = "$testing-structured"
prompt = "Invent an idea."

[pipe.judge_idea]
type = "PipeLLM"
description = "Judge the idea"
inputs = { idea = "Idea" }
output = "Verdict"
model = "$testing-structured"
prompt = "Judge this idea: $idea"

[pipe.main]
type = "PipeSequence"
description = "Invent an idea, then judge it"
output = "Verdict"
steps = [
    { pipe = "invent_idea", result = "idea" },
    { pipe = "judge_idea", result = "verdict" },
]
"""


def _open_workflow_library(*, library_id: str) -> None:
    """Open a library the way the Temporal workflow does: fresh, with its own seeded class registry, and current."""
    library = get_library_manager().open_fresh_library(library_id=library_id)
    scoped_registry = ClassRegistry()
    scoped_registry.register_classes_dict(KajsonManager.get_class_registry().get_classes_dict())
    library.set_class_registry(scoped_registry)
    set_current_library(library_id=library_id)


async def _dry_run_main_pipe(*, library_id: str) -> str:
    """Run the crate's main pipe in dry mode on the given library and return the main output's concept ref."""
    pipe = get_required_pipe(pipe_code="prevalidated.main")
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)
    pipe_job = await prepare_pipe_job(
        storage_scope="test/scope",
        user_id="pytest",
        pipe=pipe,
        library_id=library_id,
        execution_config=execution_config,
        pipe_run_mode=PipeRunMode.DRY,
        pipeline_run_id=f"{library_id}-run",
    )
    pipe_output = await pipe.run_pipe(
        job_metadata=pipe_job.job_metadata,
        working_memory=pipe_job.get_working_memory(),
        pipe_run_params=pipe_job.pipe_run_params,
    )
    main_stuff = pipe_output.main_stuff
    assert type(main_stuff.content).__name__ == main_stuff.concept.structure_class_name
    return main_stuff.concept.concept_ref


def _make_crate() -> LibraryCrate:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=PREVALIDATED_MTHDS, mthds_source="prevalidated.mthds")
    return LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])


@pytest.mark.asyncio(loop_scope="class")
class TestLoadPrevalidatedCrate:
    async def test_prevalidated_load_skips_only_validation(self, mocker: MockerFixture):
        """The same crate loads both ways into equal libraries, each runs its main pipe, and only the trusting load skips validation."""
        library_manager = get_library_manager()
        crate = _make_crate()
        validate_spy = mocker.spy(Library, "validate_library")

        validating_library_id = "prevalidated-crate-validating"
        trusting_library_id = "prevalidated-crate-trusting"
        opened_library_ids: list[str] = []
        try:
            _open_workflow_library(library_id=validating_library_id)
            opened_library_ids.append(validating_library_id)
            validating_pipes = library_manager.load_from_crate(library_id=validating_library_id, crate=crate)
            assert validate_spy.call_count == 1
            validating_library = library_manager.get_library(library_id=validating_library_id)
            assert await _dry_run_main_pipe(library_id=validating_library_id) == "prevalidated.Verdict"

            _open_workflow_library(library_id=trusting_library_id)
            opened_library_ids.append(trusting_library_id)
            trusting_pipes = library_manager.load_from_crate(library_id=trusting_library_id, crate=crate, is_crate_prevalidated=True)
            assert validate_spy.call_count == 1
            trusting_library = library_manager.get_library(library_id=trusting_library_id)
            assert await _dry_run_main_pipe(library_id=trusting_library_id) == "prevalidated.Verdict"

            # Everything but the validation happened: the same pipes, concepts and domains, the crate's
            # dynamic classes registered in the trusting library's own registry, and its fingerprint recorded.
            assert sorted(pipe.pipe_ref for pipe in trusting_pipes) == sorted(pipe.pipe_ref for pipe in validating_pipes)
            assert set(trusting_library.pipe_library.root) == set(validating_library.pipe_library.root)
            assert set(trusting_library.concept_library.root) == set(validating_library.concept_library.root)
            assert set(trusting_library.domain_library.root) == set(validating_library.domain_library.root)
            trusting_registry = trusting_library.get_class_registry()
            assert trusting_registry is not None
            for concept_ref in ("prevalidated.Idea", "prevalidated.Verdict"):
                structure_class_name = trusting_library.concept_library.get_required_concept(concept_ref=concept_ref).structure_class_name
                assert trusting_registry.has_class(name=structure_class_name)
            assert library_manager.is_crate_loaded(library_id=trusting_library_id, fingerprint=crate.fingerprint)
            assert library_manager.load_from_crate(library_id=trusting_library_id, crate=crate, is_crate_prevalidated=True) == []
        finally:
            clear_current_library()
            for library_id in opened_library_ids:
                library_manager.teardown(library_id=library_id)
