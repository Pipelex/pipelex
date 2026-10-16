"""A PipeDocGen step built from a library crate, which names its method tree by digest and carries none of its files."""

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import pytest
from mthds.method_tree.digest import digest_of_contents

from pipelex.config import get_config
from pipelex.core.memory.working_memory_factory import WorkingMemoryFactory
from pipelex.core.method_trees.method_file_store import LOCAL_METHOD_FILES, HeldFile
from pipelex.core.method_trees.tree_bundle import MethodFileRef, TreeBundleRef
from pipelex.core.pipes.exceptions import PipeLoadRefusalError
from pipelex.interpreter_hub import get_library_manager, scoped_current_library, set_current_library
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.pipe_operators.doc_gen.exceptions import PipeDocGenTemplateFileUncheckedError
from pipelex.pipe_operators.doc_gen.pipe_doc_gen import PipeDocGen
from pipelex.pipe_operators.func.direct_pipe_func_executor import TRANSPORTED_LIBRARY_ID, DirectPipeFuncExecutor
from pipelex.pipe_operators.func.pipe_func_execution_dtos import PipeFuncExecutionRequest
from pipelex.pipe_operators.func.pipe_func_execution_transport import build_pipe_func_execution_request
from pipelex.pipe_run.pipe_run_params import PipeRunParams
from pipelex.system.job_metadata import JobMetadata, RunMetadata
from pipelex.system.pipe_run_mode import PipeRunMode
from tests.integration.pipelex.pipes.operator.pipe_doc_gen.test_data import PipeDocGenTestData

_HTML_STEP = 'format = "pdf"\ntemplate_file = "invoice.html"'
_TEMPLATE = b"<h1>{{ invoice.number }}</h1>"
_HOLDER = "test_pipe_doc_gen_from_crate"
_PIPE_REF = "doc_gen_tests.print_invoice"

# One method tree holding a PipeFunc and a PipeDocGen printing from an HTML template file of the same tree.
_MIXED_MTHDS = """\
domain = "mixed_tree"
description = "A PipeFunc and a PipeDocGen template step in one method tree"

[concept.Greeting]
description = "A greeting"
[concept.Greeting.structure]
text = { type = "text", description = "the greeting text", required = true }

[concept.GreetingCard]
description = "The greeting as a printable file"
refines     = "Document"

[pipe.greet]
type = "PipeFunc"
description = "Build a greeting via customer code"
output = "Greeting"
function_name = "mixed_funcs.greet_it"

[pipe.print_greeting]
type          = "PipeDocGen"
description   = "Print the greeting"
inputs        = { greeting = "Greeting" }
output        = "GreetingCard"
format        = "pdf"
template_file = "templates/greeting.html"
"""

_MIXED_FUNC = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.system.registries.func_registry import pipe_func

from structures import mixed_tree__Greeting


@pipe_func()
async def greet_it(working_memory: WorkingMemory) -> mixed_tree__Greeting:
    return mixed_tree__Greeting(text="hello")
"""


def _crate_of_a_torn_down_library() -> LibraryCrate:
    """The crate of the test bundle sent with its template file, whose library, the only one holding its tree, is torn down."""
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    try:
        with scoped_current_library(library_id=library_id):
            library_manager.add_submitted_files(library_id=library_id, submitted_files={"invoice.html": _TEMPLATE})
            library_manager.load_from_blueprints(
                library_id=library_id,
                blueprints=[MthdsParser.make_pipelex_bundle_blueprint(mthds_content=PipeDocGenTestData.bundle(step_fields=_HTML_STEP))],
            )
            crate = library_manager.get_crate(library_id=library_id)
    finally:
        library_manager.teardown(library_id=library_id)
    assert crate is not None
    assert LOCAL_METHOD_FILES.held_tree(tree_digest=digest_of_contents({"invoice.html": _TEMPLATE})) is None
    return crate


@contextmanager
def _fresh_library() -> Generator[str, None, None]:
    library_manager = get_library_manager()
    library_id, _ = library_manager.open_library()
    try:
        with scoped_current_library(library_id=library_id):
            yield library_id
    finally:
        library_manager.teardown(library_id=library_id)


@contextmanager
def _held_template(*, template: bytes) -> Generator[str, None, None]:
    """Hold the tree of the step's template file, as a library of this process holding the method does, and name it by digest."""
    tree = LOCAL_METHOD_FILES.hold_files(holder=_HOLDER, files={"invoice.html": HeldFile.of_bytes(data=template)})
    try:
        yield tree.digest
    finally:
        LOCAL_METHOD_FILES.release(holder=_HOLDER)


@contextmanager
def _mixed_tree_request(*, tmp_path: Path) -> Generator[PipeFuncExecutionRequest, None, None]:
    """The request a sandbox-hosted deployment builds for the PipeFunc step of the mixed method, its library left open."""
    method_dir = tmp_path / "mixed_method"
    (method_dir / "mixed_funcs").mkdir(parents=True)
    (method_dir / "templates").mkdir()
    (method_dir / "mixed.mthds").write_text(_MIXED_MTHDS, encoding="utf-8")
    (method_dir / "mixed_funcs" / "__init__.py").write_text(_MIXED_FUNC, encoding="utf-8")
    (method_dir / "templates" / "greeting.html").write_text("<h1>{{ greeting.text }}</h1>", encoding="utf-8")

    pipe_func_config = get_config().interpreter.pipe_func
    previous_mode = pipe_func_config.execution_mode
    pipe_func_config.execution_mode = "local_sandbox"
    library_manager = get_library_manager()
    try:
        build_library_id, _ = library_manager.open_library()
        set_current_library(library_id=build_library_id)
        try:
            library_manager.load_libraries(library_id=build_library_id, library_dirs=[method_dir])
            yield build_pipe_func_execution_request(
                job_metadata=JobMetadata(
                    run_metadata=RunMetadata(storage_scope="test/scope", read_scope=None, user_id="user", pipeline_run_id="run")
                ),
                pipe_code="mixed_tree.greet",
                function_name="mixed_funcs.greet_it",
                working_memory=WorkingMemoryFactory.make_empty(),
                pipe_run_params=PipeRunParams(run_mode=PipeRunMode.DRY, pipe_stack_limit=10, batch_max_concurrency=None),
            )
        finally:
            library_manager.teardown(library_id=build_library_id)
    finally:
        pipe_func_config.execution_mode = previous_mode


@pytest.mark.asyncio(loop_scope="class")
@pytest.mark.usefixtures("stub_engines")
class TestPipeDocGenFromCrate:
    async def test_a_crate_validated_where_its_tree_is_held_checks_the_template_file(self) -> None:
        """The validation reads the template from the tree a library of this process holds, so the step holds its text."""
        crate = _crate_of_a_torn_down_library()

        with _held_template(template=_TEMPLATE), _fresh_library() as library_id:
            get_library_manager().load_from_crate(library_id=library_id, crate=crate)
            pipe = get_library_manager().get_library(library_id=library_id).pipe_library.get_required_pipe(pipe_code=_PIPE_REF)

        assert isinstance(pipe, PipeDocGen)
        assert pipe.template_file_text == _TEMPLATE.decode("utf-8")

    async def test_a_crate_validated_where_its_tree_is_held_reaches_the_verdict_the_template_file_gets_in_process(self) -> None:
        """A template reading a variable the step does not take is refused from the crate as from the bundle."""
        crate = _crate_of_a_torn_down_library()
        wrong_template = b"<h1>{{ invoice.number }} {{ total }}</h1>"
        crate_naming_the_wrong_template = crate.model_copy(
            update={"tree_bundles": {_PIPE_REF: TreeBundleRef(tree_digest=digest_of_contents({"invoice.html": wrong_template}), tree_path=None)}}
        )

        with _held_template(template=wrong_template), _fresh_library() as library_id, pytest.raises(PipeLoadRefusalError) as exc_info:
            get_library_manager().load_from_crate(library_id=library_id, crate=crate_naming_the_wrong_template)

        assert "Variable 'total' in the template file 'invoice.html' of PipeDocGen 'print_invoice' is not in the inputs of the pipe" in str(
            exc_info.value
        )

    async def test_a_crate_validated_where_no_library_holds_its_tree_is_refused_rather_than_passed_unchecked(self) -> None:
        crate = _crate_of_a_torn_down_library()

        with _fresh_library() as library_id, pytest.raises(PipeDocGenTemplateFileUncheckedError) as exc_info:
            get_library_manager().load_from_crate(library_id=library_id, crate=crate)

        message = str(exc_info.value)
        assert "HTML template file 'invoice.html'" in message
        assert "Validate the method where its files are" in message

    async def test_a_crate_loaded_without_validation_reads_no_file(self) -> None:
        """A worker's load of a crate its runner validated names the template by digest and reads nothing, held or not."""
        crate = _crate_of_a_torn_down_library()

        with _held_template(template=_TEMPLATE) as tree_digest, _fresh_library() as library_id:
            get_library_manager().load_from_crate(library_id=library_id, crate=crate, is_crate_prevalidated=True)
            pipe = get_library_manager().get_library(library_id=library_id).pipe_library.get_required_pipe(pipe_code=_PIPE_REF)

        assert isinstance(pipe, PipeDocGen)
        assert pipe.template_file_text is None
        assert pipe.template_file_ref == MethodFileRef(tree_digest=tree_digest, tree_path="invoice.html")

    async def test_a_transported_pipe_func_call_builds_its_sibling_template_step_by_the_crate_s_digest(self, tmp_path: Path) -> None:
        """The tree written for the call holds no bundle and a generated `structures` module: only the called step is built in it.

        The PipeDocGen step of the same tree is built as the crate names it, so it resolves its template file lexically and
        names it by the digest the crate names the tree by, the one a store serves it under.
        """
        library_manager = get_library_manager()
        with _mixed_tree_request(tmp_path=tmp_path) as request, scoped_current_library(library_id=TRANSPORTED_LIBRARY_ID):
            try:
                response = await DirectPipeFuncExecutor().run_pipe_func_transported(request=request)
                sibling = library_manager.get_library(library_id=TRANSPORTED_LIBRARY_ID).pipe_library.get_required_pipe(
                    pipe_code="mixed_tree.print_greeting"
                )
            finally:
                library_manager.teardown(library_id=TRANSPORTED_LIBRARY_ID)

        assert response.function_qualname == "greet_it"
        assert isinstance(sibling, PipeDocGen)
        assert sibling.template_file_ref == MethodFileRef(tree_digest=request.tree_digest or "", tree_path="templates/greeting.html")
