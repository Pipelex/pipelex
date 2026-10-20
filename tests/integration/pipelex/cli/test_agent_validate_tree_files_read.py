import json
from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest

from pipelex.cli.agent_cli.commands.validate._validate_core import validate_bundle_core, validate_method_folder_core
from pipelex.interpreter_hub import clear_current_library, get_current_library_id_or_none, get_library_manager
from pipelex.pipeline.validation_render import format_validate_markdown

# No `from __future__ import annotations`: the function a `PipeFunc` calls has its annotations read when it is bound.

_METHOD_MTHDS = """\
domain = "agent_tree_reads"
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
function_name = "agent_tree_reads_funcs.totals.compute_total"
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

_EXPECTED_FIELDS = {
    "tree_files_read": {
        "agent_tree_reads.bill": [],
        "agent_tree_reads.compute_total": [{"tree_path": "agent_tree_reads_funcs/totals.py", "use": "python_module"}],
        "agent_tree_reads.thank": [],
    },
    "tree_file_readers": {"agent_tree_reads_funcs/totals.py": ["agent_tree_reads.compute_total"]},
}


@pytest.fixture(name="method_dir")
def method_dir_fixture(tmp_path: Path) -> Path:
    """A method folder whose `PipeFunc` names a module of its tree, under a manifest."""
    method_dir = tmp_path / "method"
    (method_dir / "agent_tree_reads_funcs").mkdir(parents=True)
    (method_dir / "invoicing.mthds").write_text(_METHOD_MTHDS, encoding="utf-8")
    (method_dir / "agent_tree_reads_funcs" / "__init__.py").write_text("", encoding="utf-8")
    (method_dir / "agent_tree_reads_funcs" / "totals.py").write_text(_TOTALS_MODULE, encoding="utf-8")
    (method_dir / "METHODS.toml").write_text(
        '[package]\naddress = "github.com/pipelex-tests/agent-tree-reads"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    return method_dir


async def _released(validation: Awaitable[dict[str, Any]]) -> dict[str, Any]:
    """Await an agent-CLI validation, then tear down the library it leaves open and current for the process's exit.

    That library holds the tree's Python, which a later load of another tree's Python in this process would be refused
    beside. It is current in the test's own context, so it is torn down here rather than by a fixture.
    """
    try:
        return await validation
    finally:
        library_id = get_current_library_id_or_none()
        if library_id is not None:
            get_library_manager().teardown(library_id=library_id)
            clear_current_library()


@pytest.mark.asyncio(loop_scope="class")
class TestAgentValidateTreeFilesRead:
    async def test_the_method_folder_envelope_names_the_files_each_step_reads(self, method_dir: Path) -> None:
        """The envelope carries both views as JSON, in the canonical report's shapes, and its Markdown names the module."""
        result = await _released(
            validate_method_folder_core(method_dir=method_dir, library_dirs=[method_dir], allow_signatures=False, pipe_code=None)
        )

        assert {key: result[key] for key in _EXPECTED_FIELDS} == _EXPECTED_FIELDS
        assert json.loads(json.dumps(result))["tree_files_read"] == _EXPECTED_FIELDS["tree_files_read"]
        assert "- `agent_tree_reads.compute_total` reads `agent_tree_reads_funcs/totals.py` (Python module)" in format_validate_markdown(result)

    async def test_the_bundle_envelope_names_them_from_the_bundle_s_tree(self, method_dir: Path) -> None:
        """A bundle file named alone under a manifest is rooted at the manifest's folder, so its step's module is found there."""
        result = await _released(validate_bundle_core(bundle_path=method_dir / "invoicing.mthds"))

        assert {key: result[key] for key in _EXPECTED_FIELDS} == _EXPECTED_FIELDS
