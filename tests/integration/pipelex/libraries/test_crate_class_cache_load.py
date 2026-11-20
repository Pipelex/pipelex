import uuid
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from kajson.class_registry import ClassRegistry
from kajson.kajson_manager import KajsonManager
from pydantic import BaseModel
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.concepts.structure_generation.generator import StructureGenerator
from pipelex.interpreter_hub import clear_current_library, get_library_manager, get_required_pipe, set_current_library
from pipelex.libraries.crate_class_cache import CRATE_CLASS_CACHE
from pipelex.libraries.library import Library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.libraries.library_crate_factory import LibraryCrateFactory
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipeline.execution_seams import prepare_pipe_job
from pipelex.system.pipe_run_mode import PipeRunMode

IDEA_FIELDS_SCORED = """\
title = { type = "text", description = "The title", required = true }
score = { type = "integer", description = "The score", required = true }
"""

IDEA_FIELDS_TAGGED = """\
title = { type = "text", description = "The title", required = true }
tags = { type = "list", item_type = "text", description = "The tags", required = true }
"""


def _make_crate(*, domain_code: str, idea_fields: str) -> LibraryCrate:
    """A crate of two structured concepts, one naming the other, and a two-step sequence over them."""
    mthds_content = f"""\
domain = "{domain_code}"
description = "A crate loaded several times in one process"
main_pipe = "main"

[concept.Idea]
description = "An idea"

[concept.Idea.structure]
{idea_fields}
[concept.Verdict]
description = "A verdict on an idea"

[concept.Verdict.structure]
idea = {{ type = "concept", concept_ref = "{domain_code}.Idea", description = "The idea judged", required = true }}
flag = {{ type = "boolean", description = "The flag", required = true }}

[pipe.invent_idea]
type = "PipeLLM"
description = "Invent an idea"
output = "Idea"
model = "$testing-structured"
prompt = "Invent an idea."

[pipe.judge_idea]
type = "PipeLLM"
description = "Judge the idea"
inputs = {{ idea = "Idea" }}
output = "Verdict"
model = "$testing-structured"
prompt = "Judge this idea: $idea"

[pipe.main]
type = "PipeSequence"
description = "Invent an idea, then judge it"
output = "Verdict"
steps = [
    {{ pipe = "invent_idea", result = "idea" }},
    {{ pipe = "judge_idea", result = "verdict" }},
]
"""
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source=f"{domain_code}.mthds")
    return LibraryCrateFactory.make_from_blueprints(blueprints=[blueprint])


@contextmanager
def _workflow_libraries() -> Generator[list[str], None, None]:
    """The ids of the libraries a test opens, each torn down on the way out."""
    library_ids: list[str] = []
    try:
        yield library_ids
    finally:
        clear_current_library()
        for library_id in library_ids:
            get_library_manager().teardown(library_id=library_id)


def _load_like_a_workflow(*, crate: LibraryCrate, library_ids: list[str]) -> Library:
    """Load the crate the way a Temporal workflow does: a fresh library, its own seeded registry, current, trusted."""
    library_id = f"crate_class_cache_{uuid.uuid4().hex[:12]}"
    library = get_library_manager().open_fresh_library(library_id=library_id)
    library_ids.append(library_id)
    scoped_registry = ClassRegistry()
    scoped_registry.register_classes_dict(KajsonManager.get_class_registry().get_classes_dict())
    library.set_class_registry(scoped_registry)
    set_current_library(library_id=library_id)
    get_library_manager().load_from_crate(library_id=library_id, crate=crate, is_crate_prevalidated=True)
    return library


def _structure_class(*, library: Library, concept_ref: str) -> type[BaseModel]:
    structure_class_name = library.concept_library.get_required_concept(concept_ref=concept_ref).structure_class_name
    registry = library.get_class_registry()
    assert registry is not None
    structure_class = registry.get_required_class(name=structure_class_name)
    assert issubclass(structure_class, BaseModel)
    return structure_class


async def _dry_run_main_pipe(*, library_id: str, domain_code: str) -> type:
    """Run the crate's main pipe in dry mode on the given library and return its output's class."""
    set_current_library(library_id=library_id)
    pipe = get_required_pipe(pipe_code=f"{domain_code}.main")
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=False, mock_inputs=True)
    pipe_job = await prepare_pipe_job(
        storage_scope="test/scope",
        read_scope=None,
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
    return type(pipe_output.main_stuff.content)


@pytest.mark.asyncio(loop_scope="class")
class TestCrateClassCacheLoad:
    async def test_a_later_load_of_the_crate_reuses_its_classes(self, mocker: MockerFixture):
        """The second workflow library gets the first one's class objects without building any, and its run works after the first library is gone."""
        domain_code = f"cached_crate_{uuid.uuid4().hex[:8]}"
        crate = _make_crate(domain_code=domain_code, idea_fields=IDEA_FIELDS_SCORED)
        generate_spy = mocker.spy(StructureGenerator, "generate_from_structure_blueprint")
        with _workflow_libraries() as library_ids:
            first_library = _load_like_a_workflow(crate=crate, library_ids=library_ids)
            assert generate_spy.call_count == 2
            assert crate.fingerprint in CRATE_CLASS_CACHE.fingerprints()
            first_verdict_class = _structure_class(library=first_library, concept_ref=f"{domain_code}.Verdict")
            first_idea_class = _structure_class(library=first_library, concept_ref=f"{domain_code}.Idea")

            second_library = _load_like_a_workflow(crate=crate, library_ids=library_ids)
            assert generate_spy.call_count == 2
            assert _structure_class(library=second_library, concept_ref=f"{domain_code}.Verdict") is first_verdict_class
            assert _structure_class(library=second_library, concept_ref=f"{domain_code}.Idea") is first_idea_class
            assert second_library.concept_library.get_required_concept(concept_ref=f"{domain_code}.Idea") is not (
                first_library.concept_library.get_required_concept(concept_ref=f"{domain_code}.Idea")
            )
            assert sorted(second_library.pipe_library.root) == sorted(first_library.pipe_library.root)

            get_library_manager().teardown(library_id=library_ids.pop(0))
            assert await _dry_run_main_pipe(library_id=library_ids[0], domain_code=domain_code) is first_verdict_class

    async def test_another_crate_with_the_same_concept_codes_gets_its_own_classes(self):
        """Two crates declaring the same `domain.Code` with different fields each load the fields they declare."""
        domain_code = f"cached_crate_{uuid.uuid4().hex[:8]}"
        scored_crate = _make_crate(domain_code=domain_code, idea_fields=IDEA_FIELDS_SCORED)
        tagged_crate = _make_crate(domain_code=domain_code, idea_fields=IDEA_FIELDS_TAGGED)
        assert scored_crate.fingerprint != tagged_crate.fingerprint
        with _workflow_libraries() as library_ids:
            scored_library = _load_like_a_workflow(crate=scored_crate, library_ids=library_ids)
            tagged_library = _load_like_a_workflow(crate=tagged_crate, library_ids=library_ids)
            scored_again_library = _load_like_a_workflow(crate=scored_crate, library_ids=library_ids)

            scored_idea_class = _structure_class(library=scored_library, concept_ref=f"{domain_code}.Idea")
            tagged_idea_class = _structure_class(library=tagged_library, concept_ref=f"{domain_code}.Idea")
            assert tagged_idea_class is not scored_idea_class
            assert set(scored_idea_class.model_fields) == {"title", "score"}
            assert set(tagged_idea_class.model_fields) == {"title", "tags"}
            assert _structure_class(library=scored_again_library, concept_ref=f"{domain_code}.Idea") is scored_idea_class
            assert _structure_class(library=tagged_library, concept_ref=f"{domain_code}.Verdict") is not (
                _structure_class(library=scored_library, concept_ref=f"{domain_code}.Verdict")
            )

    async def test_a_library_holding_other_concepts_builds_its_own(self, mocker: MockerFixture):
        """A crate loaded beside concepts already in the library neither takes classes from the cache nor gives them."""
        holder_crate = _make_crate(domain_code=f"cached_holder_{uuid.uuid4().hex[:8]}", idea_fields=IDEA_FIELDS_SCORED)
        domain_code = f"cached_crate_{uuid.uuid4().hex[:8]}"
        crate = _make_crate(domain_code=domain_code, idea_fields=IDEA_FIELDS_SCORED)
        generate_spy = mocker.spy(StructureGenerator, "generate_from_structure_blueprint")
        with _workflow_libraries() as library_ids:
            shared_library = _load_like_a_workflow(crate=holder_crate, library_ids=library_ids)
            get_library_manager().load_from_crate(library_id=library_ids[0], crate=crate, is_crate_prevalidated=True)
            assert generate_spy.call_count == 4
            assert crate.fingerprint not in CRATE_CLASS_CACHE.fingerprints()

            fresh_library = _load_like_a_workflow(crate=crate, library_ids=library_ids)
            assert generate_spy.call_count == 6
            assert _structure_class(library=fresh_library, concept_ref=f"{domain_code}.Idea") is not (
                _structure_class(library=shared_library, concept_ref=f"{domain_code}.Idea")
            )

    async def test_zero_bound_builds_every_load(self, mocker: MockerFixture):
        """With `max_classes` at zero, every load builds the crate's classes again."""
        mocker.patch("pipelex.libraries.library_manager.crate_class_cache_max_classes", return_value=0)
        domain_code = f"cached_crate_{uuid.uuid4().hex[:8]}"
        crate = _make_crate(domain_code=domain_code, idea_fields=IDEA_FIELDS_SCORED)
        generate_spy = mocker.spy(StructureGenerator, "generate_from_structure_blueprint")
        with _workflow_libraries() as library_ids:
            first_library = _load_like_a_workflow(crate=crate, library_ids=library_ids)
            second_library = _load_like_a_workflow(crate=crate, library_ids=library_ids)
            assert generate_spy.call_count == 4
            assert crate.fingerprint not in CRATE_CLASS_CACHE.fingerprints()
            assert _structure_class(library=second_library, concept_ref=f"{domain_code}.Idea") is not (
                _structure_class(library=first_library, concept_ref=f"{domain_code}.Idea")
            )
