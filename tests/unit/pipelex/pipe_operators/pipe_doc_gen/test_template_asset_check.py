import pytest

from pipelex.core.method_trees.method_file_store import HeldFile, tree_of_held_files
from pipelex.pipe_operators.doc_gen.template_asset_check import find_template_asset_refusal, literal_template_urls, stylesheet_urls

_FILES = {
    "METHODS.toml": b'[package]\naddress = "github.com/acme/letters"\n',
    "letters.mthds": b'domain = "letters"\n',
    "templates/letter.html": b"<p>letter</p>",
    "templates/logo.png": b"\x89PNG logo",
    "styles/print.css": b'@import "base.css";\n@font-face { src: url("../fonts/brand.woff2"); }\n/* url(../fonts/commented-out.woff2) */\n',
    "styles/base.css": b"body { background: url(../images/band.png); }\n",
    "fonts/brand.woff2": b"wOF2 brand",
    "images/band.png": b"\x89PNG band",
    "funcs/private_logic.py": b"SECRET = 42\n",
}
_TREE = tree_of_held_files(files={tree_path: HeldFile.of_bytes(data=data) for tree_path, data in _FILES.items()})


def _read_file(tree_path: str) -> bytes | None:
    return _FILES.get(tree_path)


class TestTemplateAssetCheck:
    def test_the_urls_a_printer_reads_are_collected_and_the_run_s_values_skipped(self) -> None:
        template = """{# <img src="commented-out.png"> #}
<link rel="stylesheet" href="../styles/print.css"><link rel="icon" href="favicon.ico">
<img src="logo.png"><img src="{{ photo.url }}"><img src="$logo"><img src="@logo">
<a href="next-page.html">next</a><a rel="attachment" href="terms.pdf">terms</a>
<object data="chart.svg"></object><embed src="map.svg"><svg><image href="seal.png"/></svg>
<div style="background: url('paper.png')"></div>
<style>h1 { background: url(band.png); } @import 'more.css';</style>
<!-- <img src="old.png"> -->
"""

        urls = literal_template_urls(template=template)

        assert sorted(urls) == sorted(
            ["../styles/print.css", "logo.png", "terms.pdf", "chart.svg", "map.svg", "seal.png", "paper.png", "band.png", "more.css"]
        )

    def test_a_stylesheet_s_urls_skip_its_comments(self) -> None:
        stylesheet = _FILES["styles/print.css"].decode()

        assert stylesheet_urls(stylesheet=stylesheet) == ["../fonts/brand.woff2", "base.css"]

    def test_images_stylesheets_and_the_urls_they_name_pass(self) -> None:
        template = '<link rel="stylesheet" href="../styles/print.css"><img src="logo.png?v=2"><img src="https://cdn.example.com/x.png">'

        refusal = find_template_asset_refusal(
            template=template, template_label="the template file", holder="templates/letter.html", tree=_TREE, read_file=_read_file
        )

        assert refusal is None

    @pytest.mark.parametrize(
        ("template", "reference", "holder_label", "reason"),
        [
            pytest.param('<img src="missing.png">', "missing.png", "the template", "'templates/missing.png', which is not a file", id="absent"),
            pytest.param('<img src="../../logo.png">', "../../logo.png", "the template", "climbs above the root", id="outside_the_tree"),
            pytest.param('<img src="/logo.png">', "/logo.png", "the template", "starts with '/'", id="root_relative"),
            pytest.param(
                '<a rel="attachment" href="../funcs/private_logic.py">x</a>',
                "../funcs/private_logic.py",
                "the template",
                "which is not an image, a stylesheet or a font",
                id="not_an_asset",
            ),
            pytest.param(
                '<link rel="stylesheet" href="../letters.mthds">', "../letters.mthds", "the template", "which is not an image", id="a_bundle"
            ),
        ],
    )
    def test_a_literal_url_naming_no_asset_of_the_tree_is_refused(self, template: str, reference: str, holder_label: str, reason: str) -> None:
        refusal = find_template_asset_refusal(
            template=template, template_label="the template", holder="templates/letter.html", tree=_TREE, read_file=_read_file
        )

        assert refusal is not None
        assert (refusal.reference, refusal.holder_label) == (reference, holder_label)
        assert reason in refusal.reason

    def test_a_url_of_a_linked_stylesheet_is_checked_against_the_stylesheet(self) -> None:
        files = {**_FILES, "styles/base.css": b"body { background: url(../images/missing.png); }\n"}

        refusal = find_template_asset_refusal(
            template='<link rel="stylesheet" href="../styles/print.css">',
            template_label="the template",
            holder="templates/letter.html",
            tree=_TREE,
            read_file=files.get,
        )

        assert refusal is not None
        assert refusal.reference == "../images/missing.png"
        assert refusal.holder_label == "the stylesheet 'styles/base.css'"
        assert "'images/missing.png', which is not a file" in refusal.reason

    def test_an_inline_template_of_bundles_from_strings_resolves_from_the_root(self) -> None:
        refusal = find_template_asset_refusal(
            template='<img src="templates/logo.png"><img src="../logo.png">',
            template_label="the template",
            holder=None,
            tree=_TREE,
            read_file=_read_file,
        )

        assert refusal is not None
        assert refusal.reference == "../logo.png"
        assert "climbs above the root" in refusal.reason

    def test_a_bundle_named_alone_is_told_to_hand_over_its_folder(self) -> None:
        one_file_tree = tree_of_held_files(files={"letters.mthds": HeldFile.of_bytes(data=b"x")}).model_copy(update={"is_one_file": True})

        refusal = find_template_asset_refusal(
            template='<img src="logo.png">', template_label="the template", holder="letters.mthds", tree=one_file_tree, read_file=_read_file
        )

        assert refusal is not None
        assert "Hand over the method's directory instead" in refusal.reason
