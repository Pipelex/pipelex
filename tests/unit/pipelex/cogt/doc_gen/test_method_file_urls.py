import re
from urllib.parse import urljoin

import pytest
from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.vocabulary import TreeRefusalCode

from pipelex.cogt.doc_gen.method_file_urls import RelativeUrlBase, is_relative_url, template_asset_refusal
from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX, is_method_file_url

_HEX = "ab" * 32
_DIGEST = f"sha256:{_HEX}"
_TEMPLATE_BASE = RelativeUrlBase(tree_digest=_DIGEST, holder="templates/letter.html", template_label="the template file 'templates/letter.html'")
_ROOT_BASE = RelativeUrlBase(tree_digest=_DIGEST, holder=None, template_label="the inline template of PipeDocGen 'print_letter'")
_TREE_PATHS = frozenset(
    {
        "main.mthds",
        "templates/letter.html",
        "templates/logo.png",
        "templates/my logo.png",
        "styles/print.css",
        "fonts/brand.woff2",
        "assets/100%.txt",
    }
)


class TestMethodFileUrls:
    @pytest.mark.parametrize(
        ("holder", "expected"),
        [
            pytest.param("templates/letter.html", f"{METHOD_FILE_URL_PREFIX}{_HEX}/templates/letter.html", id="template_file"),
            pytest.param("my templates/100%.html", f"{METHOD_FILE_URL_PREFIX}{_HEX}/my%20templates/100%25.html", id="segments_percent_encoded"),
            pytest.param("what?#.html", f"{METHOD_FILE_URL_PREFIX}{_HEX}/what%3F%23.html", id="query_and_fragment_characters_encoded"),
            pytest.param(None, f"{METHOD_FILE_URL_PREFIX}{_HEX}/", id="root"),
        ],
    )
    def test_the_base_url_stands_for_the_holder_s_place_in_its_tree(self, holder: str | None, expected: str) -> None:
        url_base = RelativeUrlBase(tree_digest=_DIGEST, holder=holder, template_label="the template")

        assert url_base.base_url == expected
        assert is_method_file_url(url=url_base.base_url)

    @pytest.mark.parametrize(
        ("written", "expected"),
        [
            pytest.param("logo.png", "templates/logo.png", id="beside_the_template"),
            pytest.param("../styles/print.css", "styles/print.css", id="dot_dot_within_the_tree"),
            pytest.param("my%20logo.png", "templates/my logo.png", id="percent_encoded_name"),
            pytest.param("logo.png?v=2#top", "templates/logo.png", id="query_and_fragment_dropped"),
            pytest.param("../assets/100%25.txt", "assets/100%.txt", id="encoded_percent"),
            pytest.param("%2E%2E/fonts/brand.woff2", "fonts/brand.woff2", id="encoded_dot_dot_the_join_kept"),
        ],
    )
    def test_a_url_an_engine_joined_to_the_base_names_the_file_of_the_tree(self, written: str, expected: str) -> None:
        joined = urljoin(_TEMPLATE_BASE.base_url, written)

        assert _TEMPLATE_BASE.tree_path_of(url=joined, tree_paths=_TREE_PATHS) == expected

    def test_a_url_in_a_stylesheet_resolves_against_the_stylesheet(self) -> None:
        """An engine joins a stylesheet's own URLs to the stylesheet's URL, which lies in the tree too."""
        stylesheet_url = urljoin(_TEMPLATE_BASE.base_url, "../styles/print.css")
        font_url = urljoin(stylesheet_url, "../fonts/brand.woff2")

        assert _TEMPLATE_BASE.tree_path_of(url=stylesheet_url, tree_paths=_TREE_PATHS) == "styles/print.css"
        assert _TEMPLATE_BASE.tree_path_of(url=font_url, tree_paths=_TREE_PATHS) == "fonts/brand.woff2"

    @pytest.mark.parametrize(
        ("written", "code", "named"),
        [
            pytest.param("../../logo.png", TreeRefusalCode.REFERENCE_LEAVES_TREE, "climbs above the root", id="climbs_above_the_root"),
            pytest.param("../../../../../etc/passwd", TreeRefusalCode.REFERENCE_LEAVES_TREE, "climbs above the root", id="climbs_far_above"),
            pytest.param("/logo.png", TreeRefusalCode.REFERENCE_LEAVES_TREE, "starts with '/'", id="root_relative"),
            pytest.param("%2E%2E/%2E%2E/logo.png", TreeRefusalCode.REFERENCE_LEAVES_TREE, "climbs above the root", id="encoded_climb"),
            pytest.param("missing.png", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "'templates/missing.png', which is not a file", id="absent"),
            # A join turns '.' into the directory with a trailing '/', which no file's tree path ends with.
            pytest.param(".", TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH, "'templates/', which cannot name a file", id="a_directory"),
            pytest.param("..", TreeRefusalCode.REFERENCE_NOT_IN_TREE, "the root of the method tree", id="the_root"),
            pytest.param("..%2Flogo.png", TreeRefusalCode.REFERENCE_INVALID, "malformed", id="encoded_slash"),
            pytest.param("100%.png", TreeRefusalCode.REFERENCE_INVALID, "malformed", id="bare_percent"),
        ],
    )
    def test_a_joined_url_naming_no_file_of_the_tree_is_refused_naming_the_template(self, written: str, code: TreeRefusalCode, named: str) -> None:
        joined = urljoin(_TEMPLATE_BASE.base_url, written)

        with pytest.raises(MethodTreeRefusedError) as exc_info:
            _TEMPLATE_BASE.tree_path_of(url=joined, tree_paths=_TREE_PATHS)

        assert exc_info.value.refusal.code == code
        assert named in exc_info.value.message
        assert "the template file 'templates/letter.html'" in exc_info.value.message

    def test_a_url_under_another_tree_s_segment_is_refused_as_leaving_the_tree(self) -> None:
        other_tree_url = f"{METHOD_FILE_URL_PREFIX}{'cd' * 32}/templates/logo.png"

        with pytest.raises(MethodTreeRefusedError) as exc_info:
            _TEMPLATE_BASE.tree_path_of(url=other_tree_url, tree_paths=_TREE_PATHS)

        assert exc_info.value.refusal.code == TreeRefusalCode.REFERENCE_LEAVES_TREE

    def test_the_prefix_and_the_digest_are_read_without_regard_to_case(self) -> None:
        shouted = f"{METHOD_FILE_URL_PREFIX.upper()}{_HEX.upper()}/templates/logo.png"

        assert is_method_file_url(url=shouted)
        assert _TEMPLATE_BASE.tree_path_of(url=shouted, tree_paths=_TREE_PATHS) == "templates/logo.png"

    def test_a_joined_url_beside_a_bundle_named_alone_is_told_to_hand_over_its_folder(self) -> None:
        url_base = RelativeUrlBase(tree_digest=_DIGEST, holder="letters.mthds", template_label="the inline template", is_one_file_tree=True)

        with pytest.raises(MethodTreeRefusedError) as exc_info:
            url_base.tree_path_of(url=urljoin(url_base.base_url, "logo.png"), tree_paths=frozenset({"letters.mthds"}))

        assert exc_info.value.refusal.code == TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
        assert "Hand over the method's directory instead" in exc_info.value.message

    @pytest.mark.parametrize(
        ("tree_path", "is_asset"),
        [
            pytest.param("templates/logo.PNG", True, id="image_any_case"),
            pytest.param("images/seal.svg", True, id="svg"),
            pytest.param("styles/print.css", True, id="stylesheet"),
            pytest.param("fonts/brand.woff2", True, id="font"),
            pytest.param("funcs/private_logic.py", False, id="python"),
            pytest.param("letters.mthds", False, id="bundle"),
            pytest.param("METHODS.toml", False, id="manifest"),
            pytest.param("requirements.txt", False, id="requirements"),
            pytest.param("data/customers.csv", False, id="data"),
            pytest.param("templates/other.html", False, id="html"),
            pytest.param("README", False, id="no_suffix"),
        ],
    )
    def test_a_document_reads_only_images_stylesheets_and_fonts_from_its_method(self, tree_path: str, is_asset: bool) -> None:
        refusal = template_asset_refusal(tree_path=tree_path)

        assert (refusal is None) is is_asset
        if refusal is not None:
            assert f"'{tree_path}', which is not an image, a stylesheet or a font" in refusal

    def test_a_relative_url_handed_as_written_resolves_against_the_holder(self) -> None:
        assert _TEMPLATE_BASE.tree_path_of(url="../fonts/brand.woff2", tree_paths=_TREE_PATHS) == "fonts/brand.woff2"
        assert _TEMPLATE_BASE.tree_path_of(url="https://cdn.example.com/logo.png", tree_paths=_TREE_PATHS) is None
        with pytest.raises(MethodTreeRefusedError, match=re.escape("the template file 'templates/letter.html'")):
            _TEMPLATE_BASE.tree_path_of(url="../../logo.png", tree_paths=_TREE_PATHS)

    def test_a_root_base_resolves_from_the_root_and_cannot_climb_above_it(self) -> None:
        """Bundles parsed from content strings sit at the root of the tree of the files submitted with them."""
        assert _ROOT_BASE.tree_path_of(url=urljoin(_ROOT_BASE.base_url, "templates/logo.png"), tree_paths=_TREE_PATHS) == "templates/logo.png"
        assert _ROOT_BASE.tree_path_of(url="fonts/brand.woff2", tree_paths=_TREE_PATHS) == "fonts/brand.woff2"
        with pytest.raises(MethodTreeRefusedError) as exc_info:
            _ROOT_BASE.tree_path_of(url=urljoin(_ROOT_BASE.base_url, "../logo.png"), tree_paths=_TREE_PATHS)
        assert exc_info.value.refusal.code == TreeRefusalCode.REFERENCE_LEAVES_TREE
        assert "the inline template of PipeDocGen 'print_letter'" in exc_info.value.message

    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            pytest.param("logo.png", True, id="relative"),
            pytest.param("../fonts/brand.woff2", True, id="dot_dot"),
            pytest.param("/srv/photos/photo.png", False, id="root_absolute_path"),
            pytest.param("https://cdn.example.com/logo.png", False, id="https"),
            pytest.param("data:image/png;base64,iVBORw0KGgo=", False, id="data"),
            pytest.param("pipelex-storage://scope/logo.png", False, id="storage"),
            pytest.param("//cdn.example.com/logo.png", False, id="authority"),
            pytest.param("#top", False, id="fragment"),
        ],
    )
    def test_only_a_relative_url_with_a_path_names_a_file_of_the_tree(self, url: str, expected: bool) -> None:
        assert is_relative_url(url=url) is expected
