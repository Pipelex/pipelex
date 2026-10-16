import pytest
from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.vocabulary import TreeRefusalCode

from pipelex.core.method_trees.file_references import resolve_bundle_file_reference
from pipelex.core.method_trees.method_file_store import HeldFile, tree_of_held_files
from pipelex.core.method_trees.tree_bundle import TreeBundle

_SUBMITTED_FILES = ("templates/invoice.docx", "templates/letter.html", "data/rates.csv")
_SUBMITTED_TREE = tree_of_held_files(files={tree_path: HeldFile.of_bytes(data=tree_path.encode()) for tree_path in _SUBMITTED_FILES})
_BUNDLES_FROM_STRINGS = TreeBundle(tree=_SUBMITTED_TREE, tree_path=None)


class TestBundleFileReferences:
    """Bundles parsed from content strings sit at the root of the tree of the files submitted with them, so a reference resolves from the root."""

    @pytest.mark.parametrize(
        ("reference", "expected"),
        [
            pytest.param("templates/invoice.docx", "templates/invoice.docx", id="from_the_root"),
            pytest.param("templates//invoice.docx", "templates/invoice.docx", id="repeated_slash_spelled_as_keyed"),
            pytest.param("./templates/./invoice.docx", "templates/invoice.docx", id="dot_segments_spelled_as_keyed"),
            pytest.param("data/../templates/letter.html", "templates/letter.html", id="dot_dot_within_the_files"),
        ],
    )
    def test_a_reference_names_a_submitted_file_from_the_root(self, reference: str, expected: str) -> None:
        assert resolve_bundle_file_reference(reference=reference, tree_bundle=_BUNDLES_FROM_STRINGS) == expected

    @pytest.mark.parametrize(
        ("reference", "code", "resolved"),
        [
            pytest.param("templates/missing.docx", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "templates/missing.docx", id="not_submitted"),
            pytest.param("../outside.docx", TreeRefusalCode.REFERENCE_LEAVES_TREE, None, id="climbs_above_the_root"),
            pytest.param("/etc/invoice.docx", TreeRefusalCode.REFERENCE_INVALID, None, id="absolute"),
            pytest.param("https://example.com/invoice.docx", TreeRefusalCode.REFERENCE_INVALID, None, id="a_url"),
            pytest.param("templates/..", TreeRefusalCode.REFERENCE_NOT_IN_TREE, ".", id="the_root"),
        ],
    )
    def test_a_reference_naming_no_submitted_file_is_refused_with_the_standard_s_code(
        self, reference: str, code: TreeRefusalCode, resolved: str | None
    ) -> None:
        with pytest.raises(MethodTreeRefusedError) as exc_info:
            resolve_bundle_file_reference(reference=reference, tree_bundle=_BUNDLES_FROM_STRINGS)

        assert exc_info.value.refusal.code == code
        assert exc_info.value.refusal.resolved == resolved
