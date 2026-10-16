import pytest
from mthds.method_tree.exceptions import MethodTreeRefusedError

from pipelex.core.method_trees.file_references import resolve_crate_file_reference
from pipelex.core.method_trees.tree_bundle import TreeBundleRef

_TREE_DIGEST = "sha256:" + "f" * 64


class TestCrateFileReferences:
    """A pipe built from a crate resolves the file its bundle names lexically, reading nothing: the crate carries no listing."""

    @pytest.mark.parametrize(
        ("tree_path", "reference", "expected"),
        [
            ("main.mthds", "templates/invoice.docx", "templates/invoice.docx"),
            ("bundles/invoice.mthds", "../templates/invoice.html", "templates/invoice.html"),
            ("bundles/invoice.mthds", "./invoice.html", "bundles/invoice.html"),
            (None, "templates/invoice.docx", "templates/invoice.docx"),
            (None, "templates//invoice.docx", "templates/invoice.docx"),
            (None, "./templates/./invoice.docx", "templates/invoice.docx"),
        ],
        ids=[
            "beside_the_bundle",
            "climbing_in_the_tree",
            "dot_segment",
            "content_string_at_the_root",
            "repeated_slash_at_the_root",
            "dot_segments_at_the_root",
        ],
    )
    def test_a_reference_joins_the_bundle_s_tree_path(self, tree_path: str | None, reference: str, expected: str) -> None:
        tree_bundle_ref = TreeBundleRef(tree_digest=_TREE_DIGEST, tree_path=tree_path)

        assert resolve_crate_file_reference(reference=reference, tree_bundle_ref=tree_bundle_ref) == expected

    @pytest.mark.parametrize(
        ("tree_path", "reference", "reason"),
        [
            ("main.mthds", "../outside.docx", "climbs above the root"),
            (None, "../outside.docx", "climbs above the root"),
            ("main.mthds", "/etc/invoice.docx", "cannot name a file of a method tree"),
        ],
        ids=["climbs_above_the_root", "climbs_from_the_root", "absolute"],
    )
    def test_a_reference_no_tree_can_hold_is_refused(self, tree_path: str | None, reference: str, reason: str) -> None:
        tree_bundle_ref = TreeBundleRef(tree_digest=_TREE_DIGEST, tree_path=tree_path)

        with pytest.raises(MethodTreeRefusedError, match=reason):
            resolve_crate_file_reference(reference=reference, tree_bundle_ref=tree_bundle_ref)
