import pytest
from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.references import resolve_reference
from mthds.method_tree.vocabulary import ReferenceContext, TreeRefusalCode

from pipelex.core.method_trees.method_file_store import HeldFile, tree_of_held_files
from pipelex.core.method_trees.url_references import resolve_url_path, resolve_url_reference

_HOLDER = "templates/letter.html"
_TREE_PATHS = frozenset(
    {
        "main.mthds",
        "templates/letter.html",
        "templates/logo.png",
        "templates/café.png",
        "shared/logo.png",
        "assets/100%.txt",
        "images/logo.png",
        "fonts/brand.woff2",
    }
)

# A relative URL written in `templates/letter.html`, and the tree path it names, as the MTHDS conformance corpus has them.
_RESOLVED_CASES = [
    pytest.param("logo.png", "templates/logo.png", id="beside_the_template"),
    pytest.param("./logo.png", "templates/logo.png", id="dot_segment"),
    pytest.param("../shared/logo.png", "shared/logo.png", id="dot_dot_within_the_tree"),
    pytest.param("../fonts/brand.woff2", "fonts/brand.woff2", id="a_font"),
    pytest.param("logo.png?v=2#top", "templates/logo.png", id="query_and_fragment_dropped"),
    pytest.param("../assets/100%25.txt", "assets/100%.txt", id="percent_decoded"),
    pytest.param("%2E%2E/shared/logo.png", "shared/logo.png", id="encoded_dot_dot_resolves"),
    pytest.param("cafe%CC%81.png", "templates/café.png", id="nfc_normalized"),
    pytest.param("../images/logo.png/.", "images/logo.png", id="trailing_dot_segment"),
]
# A relative URL written in `templates/letter.html`, the code it is refused with, and what it resolved to.
_REFUSED_CASES = [
    pytest.param("..%2Fshared%2Flogo.png", TreeRefusalCode.REFERENCE_INVALID, None, id="encoded_slash"),
    pytest.param("../../logo.png", TreeRefusalCode.REFERENCE_LEAVES_TREE, None, id="climbs_above_the_root"),
    pytest.param("../..", TreeRefusalCode.REFERENCE_LEAVES_TREE, None, id="climbs_above_the_root_alone"),
    pytest.param("/logo.png", TreeRefusalCode.REFERENCE_INVALID, None, id="root_relative"),
    pytest.param("..\\shared\\logo.png", TreeRefusalCode.REFERENCE_INVALID, None, id="backslash"),
    pytest.param(".", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "templates", id="the_template_s_directory"),
    pytest.param("..", TreeRefusalCode.REFERENCE_NOT_IN_TREE, ".", id="the_root"),
    pytest.param("../", TreeRefusalCode.REFERENCE_NOT_IN_TREE, ".", id="the_root_with_a_slash"),
    pytest.param("../images/.", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "images", id="a_directory"),
    pytest.param("missing.png", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "templates/missing.png", id="absent"),
    pytest.param("../assets/what?.txt", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "assets/what", id="unencoded_question_mark"),
    pytest.param("../images/logo\t.png", TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH, "images/logo\t.png", id="control_character"),
    pytest.param("%0A", TreeRefusalCode.REFERENCE_INVALID, None, id="encoded_line_feed"),
    pytest.param("%00", TreeRefusalCode.REFERENCE_INVALID, None, id="encoded_nul"),
    pytest.param("%FF", TreeRefusalCode.REFERENCE_INVALID, None, id="not_utf8"),
    pytest.param("caf%E9", TreeRefusalCode.REFERENCE_INVALID, None, id="latin1"),
    pytest.param("100%.png", TreeRefusalCode.REFERENCE_INVALID, None, id="bare_percent"),
    pytest.param("%zz", TreeRefusalCode.REFERENCE_INVALID, None, id="non_hex_escape"),
    pytest.param("%4", TreeRefusalCode.REFERENCE_INVALID, None, id="short_escape"),
]
# A URL that is no file reference, left exactly as written.
_NOT_A_REFERENCE_CASES = [
    pytest.param("https://cdn.example.com/logo.png", id="https"),
    pytest.param("data:image/png;base64,iVBORw0KGgo=", id="data"),
    pytest.param("pipelex-storage://scope/assets/logo.png", id="storage"),
    pytest.param("//cdn.example.com/logo.png", id="authority"),
    pytest.param("mailto:someone@example.com", id="mailto"),
    pytest.param("", id="empty"),
    pytest.param("#top", id="fragment"),
    pytest.param("?v=2", id="query"),
]


class TestUrlReferences:
    @pytest.mark.parametrize(("reference", "expected"), _RESOLVED_CASES)
    def test_a_relative_url_resolves_against_its_holder(self, reference: str, expected: str) -> None:
        assert resolve_url_reference(reference=reference, holder=_HOLDER, tree_paths=_TREE_PATHS) == expected

    @pytest.mark.parametrize(("reference", "code", "resolved"), _REFUSED_CASES)
    def test_a_relative_url_the_standard_refuses_is_refused_with_its_code(self, reference: str, code: TreeRefusalCode, resolved: str | None) -> None:
        with pytest.raises(MethodTreeRefusedError) as exc_info:
            resolve_url_reference(
                reference=reference, holder=_HOLDER, tree_paths=_TREE_PATHS, holder_label="the template file 'templates/letter.html'"
            )

        assert exc_info.value.refusal.code == code
        assert exc_info.value.refusal.resolved == resolved
        assert "the template file 'templates/letter.html'" in exc_info.value.message

    @pytest.mark.parametrize("reference", _NOT_A_REFERENCE_CASES)
    def test_a_url_that_is_no_file_reference_is_left_as_written(self, reference: str) -> None:
        assert resolve_url_reference(reference=reference, holder=_HOLDER, tree_paths=_TREE_PATHS) is None

    @pytest.mark.parametrize(
        "written", [pytest.param(case.values[0], id=case.id) for case in (*_RESOLVED_CASES, *_REFUSED_CASES, *_NOT_A_REFERENCE_CASES)]
    )
    def test_every_answer_is_the_one_mthds_python_gives(self, written: str) -> None:
        """Run over a set of tree paths, the steps answer as `resolve_reference` does over the tree itself."""
        tree = tree_of_held_files(files={tree_path: HeldFile.of_bytes(data=tree_path.encode()) for tree_path in _TREE_PATHS})
        expected: str | TreeRefusalCode | None
        try:
            expected = resolve_reference(written, holder=_HOLDER, context=ReferenceContext.URL, tree=tree)
        except MethodTreeRefusedError as exc:
            expected = exc.refusal.code
        actual: str | TreeRefusalCode | None
        try:
            actual = resolve_url_reference(reference=written, holder=_HOLDER, tree_paths=tree.members)
        except MethodTreeRefusedError as exc:
            actual = exc.refusal.code

        assert actual == expected

    @pytest.mark.parametrize(
        ("reference", "expected"),
        [
            pytest.param("templates/logo.png", "templates/logo.png", id="from_the_root"),
            pytest.param("templates/../shared/logo.png", "shared/logo.png", id="dot_dot_within_the_tree"),
        ],
    )
    def test_a_relative_url_with_no_holder_resolves_from_the_root(self, reference: str, expected: str) -> None:
        """Bundles parsed from content strings sit at the root of the tree of the files submitted with them."""
        assert resolve_url_reference(reference=reference, holder=None, tree_paths=_TREE_PATHS) == expected

    def test_a_relative_url_with_no_holder_cannot_climb_above_the_root(self) -> None:
        with pytest.raises(MethodTreeRefusedError) as exc_info:
            resolve_url_reference(reference="../logo.png", holder=None, tree_paths=_TREE_PATHS)

        assert exc_info.value.refusal.code == TreeRefusalCode.REFERENCE_LEAVES_TREE
        assert "the root of its method tree" in exc_info.value.message

    def test_a_url_path_is_resolved_even_when_it_reads_as_a_scheme(self) -> None:
        """What an engine joined below the root is a path whatever it looks like, so a colon is refused, never left as written."""
        with pytest.raises(MethodTreeRefusedError) as exc_info:
            resolve_url_path(url_path="templates/a:b.png", reference="templates/a:b.png", holder=None, tree_paths=_TREE_PATHS)

        assert exc_info.value.refusal.code == TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
