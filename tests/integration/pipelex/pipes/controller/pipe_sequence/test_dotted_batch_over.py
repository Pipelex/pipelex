from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from pipelex.config import get_config
from pipelex.core.memory.working_memory import PRIVATE_BINDING_NAME_PREFIX, WorkingMemory
from pipelex.core.pipes.exceptions import PipeValidationError
from pipelex.core.stuffs.text_content import TextContent
from pipelex.graph.graph_tracer import GraphTracer
from pipelex.graph.graphspec import EdgeKind, GraphSpec, NodeKind, NodeSpec
from pipelex.interpreter_hub import get_library_manager
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_controllers.batch.pipe_batch import PipeBatch
from pipelex.pipe_controllers.binding.binding_step import BindingStep
from pipelex.pipe_controllers.sequence.pipe_sequence import PipeSequence
from pipelex.pipe_controllers.sub_pipe import SubPipe
from pipelex.pipe_machinery.pipe_abstract import PipeAbstract
from pipelex.pipe_run.pipe_job import PipeJob
from pipelex.pipe_run.pipe_job_factory import PipeJobFactory
from pipelex.pipe_run.pipe_run_params import BatchParams
from pipelex.pipeline.pipeline_response import PipelexRunResultExecute
from pipelex.pipeline.runner import PipelexMTHDSProtocol
from pipelex.runtime_hub import scoped_event_log
from pipelex.system.pipe_run_mode import PipeRunMode
from pipelex.tracing.in_memory_event_log import InMemoryEventLog
from pipelex.validation_error_types import PipeValidationErrorType

if TYPE_CHECKING:
    from mthds.protocol.pipeline_inputs import PipelineInputs

_CATALOG_HEADER = """domain = "catalog_index"
description = "Writing one index line for every page of a printed catalog"
main_pipe = "index_pages"

[concept.CatalogPage]
description = "A page of a printed catalog"

[concept.CatalogPage.structure]
title = { type = "text", description = "The title printed on the page", required = true }

[concept.Catalog]
description = "A printed catalog"

[concept.Catalog.structure]
season = { type = "text", description = "The season the catalog covers", required = true }
pages = { type = "list", item_type = "concept", item_concept_ref = "CatalogPage", description = "The pages of the catalog", required = true }

[pipe.write_index_line]
type = "PipeCompose"
description = "Writes the index line of one page"
inputs = { page = "CatalogPage" }
output = "Text"
template = "Page: {{ page.title }}"

[pipe.make_catalog]
type = "PipeCompose"
description = "Writes out a catalog of a season from its pages"
inputs = { season = "Text", pages = "CatalogPage[]" }
output = "Catalog"

[pipe.make_catalog.construct]
season = { from = "season.text" }
pages = { from = "pages" }
"""

_SPRING_CATALOG = {"season": "spring", "pages": [{"title": "Garden chairs"}, {"title": "Parasols"}]}
_SUMMER_CATALOG = {"season": "summer", "pages": [{"title": "Deckchairs"}]}


def _catalog_bundle(*, inputs: str, steps: list[str], output: str = "Text[]") -> str:
    """The catalog bundle with an `index_pages` sequence of these inputs, steps and output."""
    return (
        f"{_CATALOG_HEADER}\n"
        "[pipe.index_pages]\n"
        'type = "PipeSequence"\n'
        'description = "Writes one index line per page"\n'
        f"inputs = {inputs}\n"
        f'output = "{output}"\n'
        "steps = [\n" + "".join(f"  {step},\n" for step in steps) + "]\n"
    )


_SINGLE_ROOT_BUNDLE = _catalog_bundle(
    inputs='{ catalog = "Catalog" }',
    steps=['{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" }'],
)
_LIST_ROOT_BUNDLE = _catalog_bundle(
    inputs='{ catalogs = "Catalog[]" }',
    steps=['{ pipe = "write_index_line", batch_over = "catalogs.pages", batch_as = "page", result = "index_lines" }'],
)
# The root's producer is a step of the sequence, so the graph has an edge from it to the binding.
_PRODUCED_ROOT_SUGAR_BUNDLE = _catalog_bundle(
    inputs='{ season = "Text", pages = "CatalogPage[]" }',
    steps=[
        '{ pipe = "make_catalog", result = "catalog" }',
        '{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" }',
    ],
)
_PRODUCED_ROOT_EXPLICIT_BUNDLE = _catalog_bundle(
    inputs='{ season = "Text", pages = "CatalogPage[]" }',
    steps=[
        '{ pipe = "make_catalog", result = "catalog" }',
        '{ from = "catalog.pages", result = "catalog_pages" }',
        '{ pipe = "write_index_line", batch_over = "catalog_pages", batch_as = "page", result = "index_lines" }',
    ],
)
_PRODUCED_ROOT_INPUTS: "PipelineInputs" = {
    "season": "spring",
    "pages": {"concept": "catalog_index.CatalogPage", "content": _SPRING_CATALOG["pages"]},
}

_ORDER_BUNDLE_HEADER = """domain = "order_pricing"
description = "Pricing every line of an order in the customer's currency"
main_pipe = "price_order"

[concept.OrderLine]
description = "One line of an order"

[concept.OrderLine.structure]
article = { type = "text", description = "The article ordered", required = true }
amount = { type = "number", description = "What the line costs", required = true }

[concept.Order]
description = "An order placed by a customer"

[concept.Order.structure]
lines = { type = "list", item_type = "concept", item_concept_ref = "OrderLine", description = "The lines of the order", required = true }

[pipe.price_line]
type = "PipeCompose"
description = "Writes the price of one line in a currency"
inputs = { line = "OrderLine", currency = "Text" }
output = "Text"
template = "{{ line.article }}: {{ line.amount }} {{ currency.text }}"

[pipe.price_order]
type = "PipeSequence"
description = "Prices every line of an order"
inputs = { order = "Order", currency = "Text" }
output = "Text[]"
"""


def _load_sequence(*, mthds_content: str, library_id: str, pipe_code: str) -> PipeSequence:
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(mthds_content=mthds_content, mthds_source="flow.mthds")
    pipes = get_library_manager().load_from_blueprints(library_id=library_id, blueprints=[blueprint])
    sequences = [pipe for pipe in pipes if isinstance(pipe, PipeSequence) and pipe.code == pipe_code]
    assert len(sequences) == 1
    return sequences[0]


async def _index_lines(*, mthds_content: str, inputs: "PipelineInputs") -> PipelexRunResultExecute:
    return await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(mthds_contents=[mthds_content], inputs=inputs)


def _node(graph: GraphSpec, *, pipe_code: str) -> NodeSpec:
    nodes = [node for node in graph.nodes if node.pipe_code == pipe_code]
    assert len(nodes) == 1, f"expected one node for '{pipe_code}', got {[(node.kind, node.pipe_code) for node in graph.nodes]}"
    return nodes[0]


def _data_edges(graph: GraphSpec) -> set[tuple[str, str]]:
    return {(edge.source, edge.target) for edge in graph.edges if edge.kind == EdgeKind.DATA}


def _graph_shape(graph: GraphSpec) -> tuple[Counter[tuple[str, str | None, str | None]], Counter[tuple[str, str | None, str | None]]]:
    """The nodes by kind, type and pipe code, and the edges by kind and the pipe codes they join: the graph without its names."""
    pipe_codes = {node.node_id: node.pipe_code for node in graph.nodes}
    nodes = Counter((str(node.kind), node.pipe_type, node.pipe_code) for node in graph.nodes)
    edges = Counter((str(edge.kind), pipe_codes.get(edge.source), pipe_codes.get(edge.target)) for edge in graph.edges)
    return nodes, edges


async def _run_with_graph(*, mthds_content: str, inputs: "PipelineInputs") -> tuple[PipelexRunResultExecute, GraphSpec]:
    execution_config = get_config().interpreter.pipeline_execution.with_execution_overrides(generate_graph=True)
    runner = PipelexMTHDSProtocol(execution_config=execution_config, pipe_run_mode=PipeRunMode.LIVE)
    with scoped_event_log(InMemoryEventLog()):
        response = await runner.execute(mthds_contents=[mthds_content], inputs=inputs)
    graph = response.pipe_output.graph_spec
    assert graph is not None
    return response, graph


@pytest.mark.asyncio(loop_scope="class")
class TestDottedBatchOver:
    async def test_b1_a_single_root_runs_one_branch_per_page(self) -> None:
        response = await _index_lines(
            mthds_content=_SINGLE_ROOT_BUNDLE, inputs={"catalog": {"concept": "catalog_index.Catalog", "content": _SPRING_CATALOG}}
        )

        lines = [item.text for item in response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        assert lines == ["Page: Garden chairs", "Page: Parasols"]

    async def test_b2_a_list_root_runs_over_the_flattened_pages(self) -> None:
        """Regression: a dotted `batch_over` over a list root raised, since the path was read without crossing the list."""
        response = await _index_lines(
            mthds_content=_LIST_ROOT_BUNDLE,
            inputs={"catalogs": {"concept": "catalog_index.Catalog", "content": [_SPRING_CATALOG, _SUMMER_CATALOG]}},
        )

        lines = [item.text for item in response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        assert lines == ["Page: Garden chairs", "Page: Parasols", "Page: Deckchairs"]

    @pytest.mark.parametrize(
        ("mthds_content", "root_name", "root_multiplicity"),
        [
            pytest.param(_SINGLE_ROOT_BUNDLE, "catalog", None, id="a-single-root"),
            pytest.param(_LIST_ROOT_BUNDLE, "catalogs", True, id="a-list-root"),
        ],
    )
    async def test_b3_the_root_is_needed_as_its_own_concept(
        self, load_empty_library: Callable[[], str], mthds_content: str, root_name: str, root_multiplicity: bool | None
    ) -> None:
        """Regression: the sequence needed a dotted root as the batch item's concept, `CatalogPage`, with no multiplicity."""
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="index_pages")

        needed_inputs = sequence.needed_inputs()

        assert needed_inputs.variables == [root_name]
        root_need = needed_inputs.root[root_name]
        assert root_need.concept.concept_ref == "catalog_index.Catalog"
        assert root_need.multiplicity == root_multiplicity

    async def test_the_step_is_a_binding_under_a_private_name_followed_by_a_batch(self, load_empty_library: Callable[[], str]) -> None:
        sequence = _load_sequence(mthds_content=_SINGLE_ROOT_BUNDLE, library_id=load_empty_library(), pipe_code="index_pages")

        binding_step, pipe_step = sequence.sequential_sub_pipes
        assert isinstance(binding_step, BindingStep)
        assert binding_step.from_path == "catalog.pages"
        assert binding_step.is_dotted_batch_over is True
        assert binding_step.output_name == f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages"
        assert isinstance(pipe_step, SubPipe)
        assert pipe_step.batch_params is not None
        assert pipe_step.batch_params.input_list_stuff_name == binding_step.output_name
        assert pipe_step.batch_params.input_item_stuff_name == "page"
        assert sequence.build_typed_flow().binding_specs[0].multiplicity is True

    async def test_a_step_never_batches_over_a_dotted_path_itself(self) -> None:
        """Only the sequence's rewrite reads a dotted path, as a binding: a step built to batch over one is refused."""
        with pytest.raises(ValidationError) as exc_info:
            SubPipe(
                pipe_code="catalog_index.write_index_line",
                output_name="index_lines",
                batch_params=BatchParams(input_list_stuff_name="catalog.pages", input_item_stuff_name="page"),
            )

        assert "A step batches over the dotted path 'catalog.pages'" in str(exc_info.value)

    async def test_b4_a_binding_node_fed_by_the_root_producer_feeds_the_batch(self, mocker: MockerFixture) -> None:
        teardown_spy = mocker.spy(GraphTracer, "teardown")

        response, assembled_graph = await _run_with_graph(mthds_content=_PRODUCED_ROOT_SUGAR_BUNDLE, inputs=_PRODUCED_ROOT_INPUTS)

        assert [item.text for item in response.pipe_output.main_stuff_as_items(item_type=TextContent)] == ["Page: Garden chairs", "Page: Parasols"]
        in_process_graphs = [graph for graph in teardown_spy.spy_return_list if isinstance(graph, GraphSpec)]
        assert len(in_process_graphs) == 1
        for graph in (assembled_graph, in_process_graphs[0]):
            binding_node = _node(graph, pipe_code="catalog.pages")
            assert binding_node.kind == NodeKind.BINDING
            assert [io_spec.name for io_spec in binding_node.node_io.inputs] == ["catalog"]
            assert [io_spec.name for io_spec in binding_node.node_io.outputs] == [f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages"]
            producer_node = _node(graph, pipe_code="make_catalog")
            batch_node = _node(graph, pipe_code="write_index_line_batch")
            data_edges = _data_edges(graph)
            assert (producer_node.node_id, binding_node.node_id) in data_edges
            assert (binding_node.node_id, batch_node.node_id) in data_edges
            assert (producer_node.node_id, batch_node.node_id) not in data_edges

    async def test_b5_working_memory_never_holds_a_synthetic_name(self, mocker: MockerFixture) -> None:
        """Regression: the dotted path was resolved into a stuff named `catalog__pages`, of the item's concept, which no step produced."""
        batch_memory_keys: list[list[str]] = []
        make_pipe_job = PipeJobFactory.make_pipe_job

        def record_batch_memory(pipe: PipeAbstract, **kwargs: Any) -> PipeJob:
            # The keys as the batch starts, before the run adds anything to the memory or takes anything away.
            working_memory = kwargs.get("working_memory")
            if isinstance(pipe, PipeBatch) and isinstance(working_memory, WorkingMemory):
                batch_memory_keys.append(working_memory.list_keys())
            return make_pipe_job(pipe, **kwargs)

        mocker.patch.object(PipeJobFactory, "make_pipe_job", side_effect=record_batch_memory)

        response = await _index_lines(
            mthds_content=_SINGLE_ROOT_BUNDLE, inputs={"catalog": {"concept": "catalog_index.Catalog", "content": _SPRING_CATALOG}}
        )

        assert len(batch_memory_keys) == 1
        private_name = f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages"
        assert private_name in batch_memory_keys[0]
        final_keys = response.pipe_output.working_memory.list_keys()
        for keys in (batch_memory_keys[0], final_keys):
            assert "catalog__pages" not in keys
            assert not [key for key in keys if "__" in key]
        bound_pages = response.pipe_output.working_memory.get_stuff(private_name)
        assert bound_pages.concept.concept_ref == "catalog_index.CatalogPage"

    async def test_b6_the_sugar_and_the_explicit_binding_give_the_same_outputs_and_graph(self) -> None:
        sugar_response, sugar_graph = await _run_with_graph(mthds_content=_PRODUCED_ROOT_SUGAR_BUNDLE, inputs=_PRODUCED_ROOT_INPUTS)
        explicit_response, explicit_graph = await _run_with_graph(mthds_content=_PRODUCED_ROOT_EXPLICIT_BUNDLE, inputs=_PRODUCED_ROOT_INPUTS)

        sugar_lines = [item.text for item in sugar_response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        explicit_lines = [item.text for item in explicit_response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        assert sugar_lines == explicit_lines == ["Page: Garden chairs", "Page: Parasols"]
        sugar_memory = sugar_response.pipe_output.working_memory
        explicit_memory = explicit_response.pipe_output.working_memory
        sugar_pages = sugar_memory.get_stuff(f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages")
        explicit_pages = explicit_memory.get_stuff("catalog_pages")
        assert sugar_pages.concept.concept_ref == explicit_pages.concept.concept_ref == "catalog_index.CatalogPage"
        assert sugar_pages.content.model_dump() == explicit_pages.content.model_dump()
        assert _graph_shape(sugar_graph) == _graph_shape(explicit_graph)

    @pytest.mark.parametrize(
        "steps",
        [
            pytest.param(
                ['{ pipe = "price_line", batch_over = "order.lines", batch_as = "line", result = "priced_lines" }'],
                id="the-dotted-sugar",
            ),
            pytest.param(
                [
                    '{ from = "order.lines", result = "lines" }',
                    '{ pipe = "price_line", batch_over = "lines", batch_as = "line", result = "priced_lines" }',
                ],
                id="an-explicit-binding-then-a-batch",
            ),
        ],
    )
    async def test_a_batched_pipe_keeps_its_other_inputs_after_a_binding(self, load_empty_library: Callable[[], str], steps: list[str]) -> None:
        """Regression: a batched pipe's inputs besides its item were needed only when no earlier step stored the list, so after a
        binding the sequence never needed `currency`, and declaring it was refused as extraneous.
        """
        mthds_content = _ORDER_BUNDLE_HEADER + "steps = [\n" + "".join(f"  {step},\n" for step in steps) + "]\n"
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="price_order")

        assert sorted(sequence.needed_inputs().variables) == ["currency", "order"]

        response = await PipelexMTHDSProtocol(pipe_run_mode=PipeRunMode.LIVE).execute(
            mthds_contents=[mthds_content],
            inputs={
                "order": {
                    "concept": "order_pricing.Order",
                    "content": {"lines": [{"article": "Tea towel", "amount": 12.5}, {"article": "Mug", "amount": 9}]},
                },
                "currency": "euros",
            },
        )
        lines = [item.text for item in response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        assert lines == ["Tea towel: 12.5 euros", "Mug: 9.0 euros"]

    async def test_a_batch_over_a_result_that_is_not_a_plain_name_runs(self) -> None:
        """Regression: the batch a step runs was built from a blueprint, which refused any list name but a plain input name, so a
        batch over a result named `IndexLines`, which a pipe step may store under, failed when it ran.
        """
        mthds_content = _catalog_bundle(
            inputs='{ catalog = "Catalog" }',
            steps=[
                '{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "IndexLines" }',
                '{ pipe = "copy_line", batch_over = "IndexLines", batch_as = "line", result = "copied_lines" }',
            ],
        ).replace(
            "[pipe.make_catalog]",
            '[pipe.copy_line]\ntype = "PipeCompose"\ndescription = "Copies a line"\ninputs = { line = "Text" }\noutput = "Text"\n'
            'template = "Copy of $line"\n\n[pipe.make_catalog]',
        )

        response = await _index_lines(
            mthds_content=mthds_content, inputs={"catalog": {"concept": "catalog_index.Catalog", "content": _SPRING_CATALOG}}
        )

        lines = [item.text for item in response.pipe_output.main_stuff_as_items(item_type=TextContent)]
        assert lines == ["Copy of Page: Garden chairs", "Copy of Page: Parasols"]

    async def test_a_private_name_never_takes_a_name_of_the_sequence(self, load_empty_library: Callable[[], str]) -> None:
        """A pipe step may store under any name, an underscore-led one included, so the private name steps aside from it."""
        taken_name = f"{PRIVATE_BINDING_NAME_PREFIX}catalog_pages"
        mthds_content = _catalog_bundle(
            inputs='{ catalog = "Catalog" }',
            steps=[
                f'{{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "{taken_name}" }}',
                '{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" }',
            ],
        )
        sequence = _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="index_pages")

        private_names = [step.output_name for step in sequence.sequential_sub_pipes if isinstance(step, BindingStep)]
        assert private_names == [f"{taken_name}_2", f"{taken_name}_3"]

    @pytest.mark.parametrize(
        ("inputs", "steps", "error_type", "message_fragments"),
        [
            pytest.param(
                '{ catalog = "Catalog" }',
                ['{ pipe = "write_index_line", batch_over = "catalog.season", batch_as = "page", result = "index_lines" }'],
                PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                ["step 1 (pipe 'write_index_line') batches over the dotted path 'catalog.season', which derives a single 'Text', not a list"],
                id="a-path-deriving-a-single-value",
            ),
            pytest.param(
                '{ catalog = "Catalog" }',
                [
                    '{ from = "catalog.season", result = "season" }',
                    '{ pipe = "write_index_line", batch_over = "season", batch_as = "page", result = "index_lines" }',
                ],
                PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                [
                    (
                        "step 2 (pipe 'write_index_line') batches over 'season', which the binding step "
                        '{ from = "catalog.season", result = "season" } binds as a single \'Text\', not a list'
                    )
                ],
                id="an-explicit-binding-of-a-single-value",
            ),
            pytest.param(
                '{ catalog = "Catalog" }',
                [
                    '{ from = "catalog.season", result = "season" }',
                    '{ pipe = "write_title", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" }',
                ],
                PipeValidationErrorType.INPUT_STUFF_SPEC_MISMATCH,
                [
                    (
                        "step 2 (pipe 'write_title') batches over the dotted path 'catalog.pages', which derives 'CatalogPage[]', but its pipe "
                        "reads each item, 'page', as 'Number'. Declare 'page' as 'CatalogPage' in pipe 'write_title'"
                    )
                ],
                id="items-read-as-another-concept",
            ),
            pytest.param(
                '{ catalog = "Catalog" }',
                ['{ pipe = "write_index_line", batch_over = "catalog.pagez", batch_as = "page", result = "index_lines" }'],
                PipeValidationErrorType.BINDING_PATH_UNRESOLVED,
                ['the dotted `batch_over = "catalog.pagez"` cannot be derived', "has no field 'pagez'. Its fields are: 'season', 'pages'."],
                id="a-path-the-structures-cannot-walk",
            ),
            pytest.param(
                '{ season = "Text" }',
                ['{ pipe = "write_index_line", batch_over = "catalog.pages", batch_as = "page", result = "index_lines" }'],
                PipeValidationErrorType.MISSING_INPUT_VARIABLE,
                [
                    "the dotted `batch_over = \"catalog.pages\"` reads 'catalog', which is neither an input of the sequence",
                    "Declare 'catalog' in the sequence's `inputs`",
                ],
                id="a-root-nowhere",
            ),
        ],
    )
    async def test_a_dotted_batch_over_is_refused_as_a_binding_is(
        self,
        load_empty_library: Callable[[], str],
        inputs: str,
        steps: list[str],
        error_type: PipeValidationErrorType,
        message_fragments: list[str],
    ) -> None:
        mthds_content = _catalog_bundle(inputs=inputs, steps=steps).replace(
            "[pipe.make_catalog]",
            '[pipe.write_title]\ntype = "PipeCompose"\ndescription = "Writes a title"\ninputs = { page = "Number" }\noutput = "Text"\n'
            'template = "Number $page"\n\n[pipe.make_catalog]',
        )

        with pytest.raises(PipeValidationError) as exc_info:
            _load_sequence(mthds_content=mthds_content, library_id=load_empty_library(), pipe_code="index_pages")

        assert exc_info.value.error_type == error_type
        message = str(exc_info.value)
        for fragment in message_fragments:
            assert fragment in message, f"'{fragment}' not in: {message}"
