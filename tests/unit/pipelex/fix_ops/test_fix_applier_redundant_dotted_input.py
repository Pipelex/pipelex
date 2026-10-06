import pytest
import tomlkit

from pipelex.fix_ops.applier import FixOpOutcome, apply_fix_ops, serialize_and_format
from pipelex.suggested_fix import DeleteKeyOp

_INPUTS_TABLE_PATH = ["pipe", "describe_page", "inputs"]

_INLINE_SOURCE = """[pipe.describe_page]
type = "PipeLLM"
description = "Describe the view of a catalog page"
# The dotted key is redundant: its root is declared beside it.
inputs = { "page.page_view" = "Image", page = "Page" }
output = "Text"
prompt = "Describe @page.page_view"
"""

_BLOCK_SOURCE = """[pipe.describe_page]
type = "PipeLLM"
description = "Describe the view of a catalog page"
output = "Text"
prompt = "Describe @page.page_view"

[pipe.describe_page.inputs]
"page.page_view" = "Image"
page = "Page"
"""


class TestFixApplierRedundantDottedInput:
    @pytest.mark.parametrize("source", [_INLINE_SOURCE, _BLOCK_SOURCE], ids=["inline-table", "block-table"])
    def test_delete_drops_the_quoted_dotted_key_and_keeps_its_root(self, source: str) -> None:
        """At the applier, the `delete-redundant-dotted-input` op removes the quoted key as one flat key, never a nested path."""
        toml_doc = tomlkit.loads(source)

        applications = apply_fix_ops(toml_doc=toml_doc, ops=[DeleteKeyOp(table_path=_INPUTS_TABLE_PATH, key="page.page_view")])

        assert [application.outcome for application in applications] == [FixOpOutcome.APPLIED]
        formatted = serialize_and_format(toml_doc)
        assert 'page.page_view" =' not in formatted
        reloaded = tomlkit.loads(formatted).unwrap()
        assert reloaded["pipe"]["describe_page"]["inputs"] == {"page": "Page"}
        assert reloaded["pipe"]["describe_page"]["prompt"] == "Describe @page.page_view"

    def test_applying_twice_is_idempotent(self) -> None:
        """Re-applying finds the key already gone: the op is skipped and the bytes hold."""
        toml_doc = tomlkit.loads(_INLINE_SOURCE)
        ops = [DeleteKeyOp(table_path=_INPUTS_TABLE_PATH, key="page.page_view")]
        apply_fix_ops(toml_doc=toml_doc, ops=ops)
        once = serialize_and_format(toml_doc)

        applications = apply_fix_ops(toml_doc=toml_doc, ops=ops)

        assert [application.outcome for application in applications] == [FixOpOutcome.SKIPPED]
        assert serialize_and_format(toml_doc) == once
