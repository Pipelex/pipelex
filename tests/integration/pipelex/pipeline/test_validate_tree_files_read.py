from pathlib import Path

import pytest

from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.method_trees.tree_file_reads import TreeFileRead, TreeFileUse
from pipelex.core.stuffs.text_content import TextContent
from pipelex.pipeline.validate_in_process import validate_bundles_in_process
from pipelex.system.registries.func_registry import pipe_func

# No `from __future__ import annotations`: the function a `PipeFunc` calls has its annotations read when it is bound.

_INVOICING_MTHDS = """\
domain = "tree_reads"
main_pipe = "bill"

[pipe.bill]
type = "PipeSequence"
description = "Total the invoice, then thank the customer"
inputs = { text = "Text" }
output = "Text"
steps = [{ pipe = "compute_total", result = "total" }, { pipe = "thank", result = "thanks" }]

[pipe.compute_total]
type = "PipeFunc"
description = "Total the invoice"
function_name = "tree_reads_funcs.totals.compute_total"
output = "Text"

[pipe.thank]
type = "PipeCompose"
description = "Thank the customer"
inputs = { text = "Text" }
output = "Text"
template = "Thank you, $text"
"""

_TOTALS_MODULE = """\
from pipelex.core.memory.working_memory import WorkingMemory
from pipelex.core.stuffs.text_content import TextContent
from pipelex.system.registries.func_registry import pipe_func


@pipe_func()
async def compute_total(working_memory: WorkingMemory) -> TextContent:
    return TextContent(text="42")
"""


# A bundle sent as a string, whose `PipeFunc` finds its function on this process's import path: this very module.
_IMPORT_PATH_MTHDS = """\
domain = "tree_reads_import_path"

[pipe.compute_total]
type = "PipeFunc"
description = "Total the invoice"
function_name = "tests.integration.pipelex.pipeline.test_validate_tree_files_read.tree_reads_compute_total"
output = "Text"
"""


@pipe_func()
def tree_reads_compute_total(working_memory: WorkingMemory) -> TextContent:  # ruff: ignore[unused-function-argument]  # pyright: ignore[reportUnusedParameter]
    return TextContent(text="42")


def _write_method(*, method_dir: Path, module_tree_path: str) -> None:
    """A method folder whose `PipeFunc` names its module by import path, beside a file no step reads."""
    files = {
        "invoicing.mthds": _INVOICING_MTHDS,
        "tree_reads_funcs/__init__.py": "",
        module_tree_path: _TOTALS_MODULE,
        "README.md": "# Invoicing\n",
    }
    for tree_path, text in files.items():
        (method_dir / tree_path).parent.mkdir(parents=True, exist_ok=True)
        (method_dir / tree_path).write_text(text, encoding="utf-8")


@pytest.mark.asyncio(loop_scope="class")
class TestValidateTreeFilesRead:
    @pytest.mark.parametrize(
        "module_tree_path",
        [
            pytest.param("tree_reads_funcs/totals.py", id="module_file"),
            pytest.param("tree_reads_funcs/totals/__init__.py", id="package"),
        ],
    )
    async def test_the_report_names_the_module_of_each_pipe_func_and_an_empty_list_for_every_other_pipe(
        self, tmp_path: Path, module_tree_path: str
    ) -> None:
        """The module is the file the import path resolves to in the tree; a controller and a compose step read no file."""
        method_dir = tmp_path / "method"
        _write_method(method_dir=method_dir, module_tree_path=module_tree_path)

        report = await validate_bundles_in_process(method_dir=method_dir, library_dirs_are_callers=True)

        assert report.tree_files_read == {
            "tree_reads.bill": [],
            "tree_reads.compute_total": [TreeFileRead(tree_path=module_tree_path, use=TreeFileUse.PYTHON_MODULE)],
            "tree_reads.thank": [],
        }
        # Keyed exactly like the contracts: every validated pipe, whether or not it reads a file.
        assert set(report.tree_files_read) == set(report.pipe_io_contracts)
        # The package's `__init__.py`, the bundle and the README are files no step reads.
        assert report.tree_file_readers == {module_tree_path: ["tree_reads.compute_total"]}
        assert report.model_dump(mode="json")["tree_files_read"]["tree_reads.compute_total"] == [
            {"tree_path": module_tree_path, "use": "python_module"}
        ]

    async def test_a_function_found_on_the_import_path_is_no_file_of_a_tree(self) -> None:
        """A bundle sent as a string with no file beside it belongs to no tree, so its step reads no file a report can name."""
        report = await validate_bundles_in_process(mthds_contents=[_IMPORT_PATH_MTHDS])

        assert report.tree_files_read == {"tree_reads_import_path.compute_total": []}
        assert report.tree_file_readers == {}
