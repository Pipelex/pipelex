"""The files an HTML template names by literal relative URLs, checked in its method tree when the method loads.

A relative URL in an HTML template names an image, a stylesheet or a font of the template's method tree, which the print
reads (`pipelex.cogt.doc_gen.method_file_urls`). A URL the template writes as it is, such as `<img src="logo.png">`, is
the method's own, so it is checked when the method loads, where a missing or misspelt file is the author's to fix,
rather than at its first live print: each is resolved in the tree by the MTHDS standard's rules, must name an image, a
stylesheet or a font, and a stylesheet's own URLs are checked against the stylesheet, from its bytes in the tree.

Only literal URLs are checked. A value holding a template expression or a sigil, such as `src="{{ photo.url }}"` or
`href="$link"`, is the run's, and is checked when the document prints. What is read is what a printer reads from HTML:
an image's `src`, an embedded object, a linked stylesheet or attachment, an SVG image, and every `url()` and `@import`
of a stylesheet, an inline one or a `style` attribute included. A Jinja comment is skipped, and so is a CSS comment.

The check also says which files of the tree those literal URLs name, so the step can tell a validation the files its
print reads beside its template (`pipelex.core.method_trees.tree_file_reads`).
"""

import re
from collections.abc import Callable
from html.parser import HTMLParser
from typing import NamedTuple

from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.models import MethodTree
from mthds.method_tree.references import is_file_reference, resolve_reference
from mthds.method_tree.vocabulary import ReferenceContext
from typing_extensions import override

from pipelex.cogt.doc_gen.method_file_urls import template_asset_refusal
from pipelex.core.method_trees.url_references import resolve_url_reference

#: A Jinja comment, which renders as nothing.
_JINJA_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)
#: A CSS comment, which names nothing.
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
#: A `url()` of a stylesheet, quoted or not.
_CSS_URL = re.compile(r"""url\(\s*(?:"([^"]*)"|'([^']*)'|([^)\s'"]*))\s*\)""", re.IGNORECASE)
#: An `@import` naming its stylesheet by a quoted string; one written with `url()` is a `url()`.
_CSS_IMPORT = re.compile(r"""@import\s+(?:"([^"]*)"|'([^']*)')""", re.IGNORECASE)
#: What marks a value as the run's rather than the template's: a Jinja expression or statement, or a sigil.
_TEMPLATE_VALUE_MARKERS = ("{", "$", "@")
#: The suffix of a stylesheet, whose own URLs are checked against it.
_STYLESHEET_SUFFIX = ".css"
#: The `rel` tokens of a `<link>` or an `<a>` whose `href` a printer reads.
_READ_LINK_RELS = frozenset({"stylesheet", "attachment"})
#: The attributes of each element whose URL a printer reads.
_URL_ATTRIBUTES: dict[str, tuple[str, ...]] = {
    "img": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "image": ("href", "xlink:href"),
}


class TemplateAssetRefusal(NamedTuple):
    """A literal URL of a template that names no image, stylesheet or font of its method tree, and why."""

    reference: str
    holder_label: str
    reason: str


class TemplateAssetCheck(NamedTuple):
    """What checking an HTML template's literal relative URLs found: the files of the tree they name, and the first refusal.

    `asset_tree_paths` holds each image, stylesheet and font the template or one of its stylesheets names, by tree path,
    once, in the order the check reached it; when the check refuses a URL, it holds those reached before it.
    """

    asset_tree_paths: list[str]
    refusal: TemplateAssetRefusal | None


class _HtmlUrls(HTMLParser):
    """The URLs an HTML template names that a printer reads, as written."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.urls: list[str] = []
        self._in_style = False

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name: value for name, value in attrs if value is not None}
        for attribute in _URL_ATTRIBUTES.get(tag, ()):
            if attribute in attributes:
                self.urls.append(attributes[attribute])
        if tag in {"link", "a"} and "href" in attributes:
            rels = set(attributes.get("rel", "").lower().split())
            if rels & _READ_LINK_RELS:
                self.urls.append(attributes["href"])
        if "style" in attributes:
            self.urls.extend(stylesheet_urls(stylesheet=attributes["style"]))
        if tag == "style":
            self._in_style = True

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag == "style":
            self._in_style = False

    @override
    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.urls.extend(stylesheet_urls(stylesheet=data))


def stylesheet_urls(*, stylesheet: str) -> list[str]:
    """The URLs a stylesheet names, by `url()` or `@import`, as written, its comments skipped."""
    text = _CSS_COMMENT.sub("", stylesheet)
    urls: list[str] = []
    for pattern in (_CSS_URL, _CSS_IMPORT):
        for match in pattern.finditer(text):
            urls.append(next(group for group in match.groups() if group is not None))
    return urls


def literal_template_urls(*, template: str) -> list[str]:
    """The URLs an HTML template writes as they are, which a printer reads: none holding an expression or a sigil."""
    parser = _HtmlUrls()
    parser.feed(_JINJA_COMMENT.sub("", template))
    parser.close()
    return [url for url in parser.urls if not any(marker in url for marker in _TEMPLATE_VALUE_MARKERS)]


def check_template_assets(
    *, template: str, template_label: str, holder: str | None, tree: MethodTree, read_file: Callable[[str], bytes | None]
) -> TemplateAssetCheck:
    """Resolve each literal relative URL of an HTML template in its method tree, and find the first that names no asset.

    Args:
        template: The template's text, as written.
        template_label: How a refusal names the template: "the template file 'templates/invoice.html'".
        holder: The tree path of the file the template belongs to: the template file, or the bundle of an inline
            template; None for bundles parsed from content strings, at the root of the tree of the files sent with them.
        tree: The template's method tree, as this process holds it.
        read_file: Reads a file of the tree by its tree path, for a stylesheet's own URLs; None when it cannot.

    Returns:
        The images, stylesheets and fonts the URLs name, by tree path, and the refusal of the first URL that names no
        image, stylesheet or font of the tree, None when every one does.
    """
    asset_tree_paths: list[str] = []
    checked_stylesheets: set[str] = set()
    pending: list[tuple[str, str | None, str]] = [(url, holder, template_label) for url in literal_template_urls(template=template)]
    while pending:
        reference, url_holder, holder_label = pending.pop(0)
        try:
            tree_path = _resolve(reference=reference, holder=url_holder, tree=tree)
        except MethodTreeRefusedError as exc:
            refusal = TemplateAssetRefusal(reference=reference, holder_label=holder_label, reason=exc.message)
            return TemplateAssetCheck(asset_tree_paths=asset_tree_paths, refusal=refusal)
        if tree_path is None:
            continue
        asset_refusal = template_asset_refusal(tree_path=tree_path)
        if asset_refusal is not None:
            refusal = TemplateAssetRefusal(reference=reference, holder_label=holder_label, reason=asset_refusal)
            return TemplateAssetCheck(asset_tree_paths=asset_tree_paths, refusal=refusal)
        if tree_path not in asset_tree_paths:
            asset_tree_paths.append(tree_path)
        if not tree_path.lower().endswith(_STYLESHEET_SUFFIX) or tree_path in checked_stylesheets:
            continue
        checked_stylesheets.add(tree_path)
        stylesheet = _stylesheet_text(data=read_file(tree_path))
        if stylesheet is not None:
            stylesheet_label = f"the stylesheet '{tree_path}'"
            pending.extend((url, tree_path, stylesheet_label) for url in stylesheet_urls(stylesheet=stylesheet))
    return TemplateAssetCheck(asset_tree_paths=asset_tree_paths, refusal=None)


def _resolve(*, reference: str, holder: str | None, tree: MethodTree) -> str | None:
    """The tree path a URL names from its holder, by `mthds-python` when the holder is a file of the tree.

    Its refusals then name the membership rule that keeps a file out, and the one-file tree of a bundle named alone.
    """
    if not is_file_reference(reference, context=ReferenceContext.URL):
        return None
    if holder is not None:
        return resolve_reference(reference, holder=holder, context=ReferenceContext.URL, tree=tree)
    return resolve_url_reference(reference=reference, holder=None, tree_paths=tree.members, is_one_file_tree=tree.is_one_file)


def _stylesheet_text(*, data: bytes | None) -> str | None:
    """A stylesheet's text, or None when it cannot be read as UTF-8, its own URLs then left to the print."""
    if data is None:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeError:
        return None
