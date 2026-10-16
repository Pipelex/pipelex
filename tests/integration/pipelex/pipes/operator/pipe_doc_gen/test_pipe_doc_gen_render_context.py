"""What a PipeDocGen step's HTML template file is printed with, and the libraries that type it where the run's is not held."""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager

import pytest
from pytest_mock import MockerFixture

from pipelex.cogt.doc_gen.document_composition import ComposedTemplateFile
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.interpreter_hub import get_concept_library, get_library_manager, scoped_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.doc_gen.template_file_stage import RENDER_LIBRARIES, DocGenTemplateFileStage, RenderLibraryCache
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_TEMPLATE = "<h1>{{ invoice.number }}</h1>"
_PIPE_REF = "doc_gen_tests.print_invoice"

_OTHER_CONCEPTS_MTHDS = """
domain = "render_library_tests"

[concept.Receipt]
description = "A receipt"
"""


@asynccontextmanager
async def _composed_template_file() -> AsyncGenerator[tuple[ComposedTemplateFile, LibraryCrate], None]:
    """The template file the test bundle's step composes from a memory holding a stuff no input names, with the run's crate.

    The run's library is open for the block, and torn down after it.
    """
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    try:
        with scoped_current_library(library_id=library_id):
            library_manager.add_submitted_files(library_id=library_id, submitted_files={"invoice.html": _TEMPLATE.encode("utf-8")})
            bundle = PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate_file = "invoice.html"')
            library_manager.load_from_blueprints(library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=bundle)])
            crate = library_manager.get_crate(library_id=library_id)
            assert crate is not None
            pipe = library_manager.get_library(library_id=library_id).pipe_library.get_required_pipe(pipe_code=_PIPE_REF)
            assert isinstance(pipe, PipeDocGen)
            working_memory = WorkingMemoryFactory.make_from_pipeline_inputs(
                {**PipeDocGenTestData.INVOICE_INPUTS, "unread": {"concept": "Text", "content": "Read by no template"}},
                concept_provider=get_concept_library(),
                read_scope=None,
            )
            composition = await pipe.compose(
                working_memory=working_memory,
                pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
            )
            assert composition.template_file is not None
            yield composition.template_file, crate
    finally:
        library_manager.teardown(library_id=library_id)


@pytest.fixture
def released_render_libraries() -> Generator[None, None, None]:
    yield
    RENDER_LIBRARIES.release_idle()


def _concepts_crate(*, mthds_content: str) -> LibraryCrate:
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    try:
        with scoped_current_library(library_id=library_id):
            library_manager.load_from_blueprints(
                library_id=library_id, blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content)]
            )
            crate = library_manager.get_crate(library_id=library_id)
    finally:
        library_manager.teardown(library_id=library_id)
    assert crate is not None
    return crate.concepts_only()


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("stub_engines")
class TestPipeDocGenRenderContext:
    async def test_the_print_receives_the_stuffs_the_step_s_inputs_name_and_the_run_s_concepts_alone(self) -> None:
        """The composition crosses into the print activity's payload, so it carries neither the run's pipes nor data no input names."""
        async with _composed_template_file() as (template_file, crate):
            render_context = template_file.render_context

        assert render_context is not None
        assert set(render_context.working_memory_raw["root"]) == {"invoice"}
        assert render_context.crate_fingerprint == crate.fingerprint
        assert render_context.concepts_crate == crate.concepts_only().model_dump(mode="json")
        assert render_context.concepts_crate["pipes"] == {}
        assert render_context.concepts_crate["tree_bundles"] == {}
        assert "doc_gen_tests.Invoice" in render_context.concepts_crate["concepts"]

    @pytest.mark.usefixtures("released_render_libraries")
    async def test_prints_away_from_the_run_s_library_type_their_data_in_one_library_kept_for_the_concepts(self, mocker: MockerFixture) -> None:
        """Loading the concepts builds their classes, so the library typing a print's data is kept for the next print."""
        async with _composed_template_file() as (template_file, _crate):
            pass
        load_spy = mocker.spy(get_library_manager(), "load_from_crate")
        stage = DocGenTemplateFileStage()

        first = await stage.render_html_template_file(template_file=template_file, template_source=_TEMPLATE)
        second = await stage.render_html_template_file(template_file=template_file, template_source=_TEMPLATE)

        assert first == second == "<h1>INV-2026-0142</h1>"
        load_spy.assert_called_once()
        assert len(RENDER_LIBRARIES.held_library_ids()) == 1

    async def test_libraries_no_print_uses_are_torn_down_beyond_the_capacity_and_one_torn_down_elsewhere_is_loaded_again(self) -> None:
        library_manager = get_library_manager()
        cache = RenderLibraryCache(capacity=1)
        invoice_concepts = _concepts_crate(mthds_content=PipeDocGenTestData.bundle(step_fields='format = "pdf"\ntemplate = "<h1></h1>"'))
        receipt_concepts = _concepts_crate(mthds_content=_OTHER_CONCEPTS_MTHDS)
        try:
            with cache.library_for(concepts_crate=invoice_concepts) as invoice_library_id:
                with cache.library_for(concepts_crate=receipt_concepts) as receipt_library_id:
                    # Both are in use, so neither is torn down past the capacity.
                    assert cache.held_library_ids() == [invoice_library_id, receipt_library_id]
                assert cache.held_library_ids() == [invoice_library_id, receipt_library_id]
            # Both idle: the least recently used goes past the capacity.
            assert cache.held_library_ids() == [receipt_library_id]
            assert not library_manager.is_crate_loaded(library_id=invoice_library_id, fingerprint=invoice_concepts.fingerprint)

            library_manager.teardown(library_id=receipt_library_id)
            with cache.library_for(concepts_crate=receipt_concepts) as reloaded_library_id:
                assert reloaded_library_id != receipt_library_id
                assert library_manager.is_crate_loaded(library_id=reloaded_library_id, fingerprint=receipt_concepts.fingerprint)
        finally:
            cache.release_idle()
        assert cache.held_library_ids() == []
