"""Where a relative URL of an HTML document resolves: a file of its template's method tree, named by a URL no network serves.

An HTML template names the files beside it in its method tree by relative URLs: an image's `src`, a stylesheet's `href`,
and the fonts and images a stylesheet names with `url()`. Each is a file reference in URL context, resolved against the
tree path of the file that holds it (`pipelex.core.method_trees.url_references`). An engine resolves a relative URL as
HTML and CSS do, by joining it to the URL of the file that holds it, which is how a stylesheet's own URLs resolve against
the stylesheet rather than the template. So the print hands the engine a base URL standing for the template's place in
its tree, `RenderJob.base_url`, under `METHOD_FILE_URL_PREFIX`, whose host no network serves. The engine reads a URL it
joined under the prefix through `RenderResources.load`, and the print maps it back to the tree path it names, looks that
path up in the tree's listing and reads the file through the method file store. Nothing is ever read from a disk.

The prefix is followed by the tree's digest, as its 64 hexadecimal digits, then by the holder's tree path, each segment
percent-encoded. The digest's segment is how a URL that climbed above the root is told from one inside the tree: a join
removes each `..` it can, so a URL that climbed out lands beside that segment, or above it, and is refused as leaving the
tree, and so is a root-relative URL such as `/logo.png`, which lands there too. Below the digest's segment, the URL's path
is a path from the root, resolved by the standard's steps from the root: each segment percent-decoded, the result in NFC,
a `..` the join left, such as a percent-encoded one, resolved lexically, the result checked to be a tree path and looked
up. A relative URL an engine hands as written, without joining it, is resolved against the holder by the same steps.

An engine's join applies RFC 3986's removal of dot segments, which parts from the standard's lexical resolution in a few
corner spellings: Python's `urljoin`, which WeasyPrint uses, drops an empty segment, so `a//b` names `a/b` where the
standard refuses it, and turns a trailing `/.` into `/`, so `logo.png/.` is refused where the standard resolves it. None
of these reaches a file outside the tree, since whatever the engine joined, the print reads only a file the tree's listing
names. A URL that climbs out of the tree and back in through the digest's segment resolves inside the tree as well, and
the template's author cannot write one: the digest is that of a tree holding the template itself.
"""

from collections.abc import Set as AbstractSet
from urllib.parse import quote

from mthds.method_tree.digest import DIGEST_PREFIX
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeRefusal
from mthds.method_tree.references import ROOT_RESOLVED, is_file_reference
from mthds.method_tree.vocabulary import ReferenceContext, TreeRefusalCode
from pydantic import BaseModel, ConfigDict, Field

from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX
from pipelex.core.method_trees.url_references import resolve_url_path, resolve_url_reference, url_path_of


def is_method_file_url(*, url: str) -> bool:
    """Whether `url` lies under `METHOD_FILE_URL_PREFIX`, where it names a file of a document's method tree.

    A URL's scheme and host are compared without regard to letter case, as URLs compare them.
    """
    return url[: len(METHOD_FILE_URL_PREFIX)].lower() == METHOD_FILE_URL_PREFIX


def is_relative_url(*, url: str) -> bool:
    """Whether `url` is a relative URL with a path, which in an HTML document names a file of its method tree.

    A URL naming a scheme (`https:`, `data:`, `pipelex-storage:`), one holding an authority (`//host/x`) and one with no
    path (`#top`, `?v=2`, the empty URL) are not: each is read as what it names, or left as written.
    """
    return is_file_reference(url, context=ReferenceContext.URL)


class RelativeUrlBase(BaseModel):
    """Where an HTML document's template sits in its method tree, which every relative URL of the document resolves against.

    The composition of a step printing from an HTML template of a method tree carries it, across the workflow boundary
    on a distributed orchestrator, so it is plain data: the tree's digest, the holder's tree path, and how a refusal names
    the template.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tree_digest: str = Field(description="The digest of the template's method tree, 'sha256:' and 64 lowercase hexadecimal digits")
    holder: str | None = Field(
        description=(
            "The tree path of the file holding the template: the template file, or the bundle of an inline template. None "
            "for an inline template of bundles parsed from content strings, which sit at the root of the tree of the files "
            "submitted with them without being a file of it, so their relative URLs resolve from the root"
        )
    )
    template_label: str = Field(description="How a refusal names the template: \"the template file 'templates/letter.html'\"")

    @property
    def base_url(self) -> str:
        """The URL an engine joins a relative URL of the document to: the holder's place in its tree, under the prefix."""
        root_url = f"{METHOD_FILE_URL_PREFIX}{self._tree_segment}/"
        if self.holder is None:
            return root_url
        return root_url + "/".join(quote(segment, safe="") for segment in self.holder.split("/"))

    @property
    def _tree_segment(self) -> str:
        return self.tree_digest.removeprefix(DIGEST_PREFIX)

    def tree_path_of(self, *, url: str, tree_paths: AbstractSet[str]) -> str | None:
        """The tree path of the file a URL of the document names, by the standard's steps for a relative URL.

        Args:
            url: A URL an engine joined under `METHOD_FILE_URL_PREFIX`, or a URL of the document as written, which
                resolves against the holder.
            tree_paths: The tree paths of the tree's files, as its listing names them.

        Returns:
            The tree path the URL names, or None for a URL as written that is no relative URL, such as an `https://`
            or a `data:` URL, which names no file of the tree.

        Raises:
            MethodTreeRefusedError: The URL names no file of the tree; `refusal.code` is the standard's code for why,
                and the message says so naming the template.
        """
        if is_method_file_url(url=url):
            return self._tree_path_of_joined(url=url, tree_paths=tree_paths)
        return resolve_url_reference(reference=url, holder=self.holder, tree_paths=tree_paths, holder_label=self.template_label)

    def _tree_path_of_joined(self, *, url: str, tree_paths: AbstractSet[str]) -> str:
        """The tree path a URL an engine joined under the prefix names, resolved from the root below the tree's segment."""
        tree_segment, _separator, below_root = url_path_of(reference=url[len(METHOD_FILE_URL_PREFIX) :]).partition("/")
        if tree_segment != self._tree_segment:
            # A join removes each `..` it can, so a URL that climbed above the root, or one written from it, lands
            # outside the tree's own segment.
            msg = f"Its relative URL climbs above the root of the method tree of {self.template_label}, or starts with '/'."
            raise MethodTreeRefusedError(msg, refusal=TreeRefusal(code=TreeRefusalCode.REFERENCE_LEAVES_TREE, names=[below_root]))
        try:
            return resolve_url_path(url_path=below_root, reference=below_root, holder=None, tree_paths=tree_paths)
        except MethodTreeRefusedError as exc:
            msg = self._joined_refusal_message(refusal=exc.refusal)
            raise MethodTreeRefusedError(msg, refusal=exc.refusal) from exc

    def _joined_refusal_message(self, *, refusal: TreeRefusal) -> str:
        """Why a URL an engine joined names no file of the tree, naming what it resolved to, since the URL as written is the engine's."""
        tree_label = f"the method tree of {self.template_label}"
        match refusal.code:
            case TreeRefusalCode.REFERENCE_INVALID:
                return (
                    f"Its relative URL is malformed in {tree_label}: its path holds a backslash, a '%' not followed by two "
                    "hexadecimal digits, or a percent-escape that decodes to a '/', a backslash, a control character or bytes that are not UTF-8."
                )
            case TreeRefusalCode.REFERENCE_LEAVES_TREE:
                return f"Its relative URL climbs above the root of {tree_label}."
            case TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH:
                return f"Its relative URL resolves to '{refusal.resolved}', which cannot name a file of {tree_label}."
            case TreeRefusalCode.REFERENCE_NOT_IN_TREE:
                if refusal.resolved == ROOT_RESOLVED:
                    return f"Its relative URL resolves to the root of {tree_label}, which is not a file."
                return f"Its relative URL resolves to '{refusal.resolved}', which is not a file of {tree_label}."
            case (
                TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE
                | TreeRefusalCode.SYMBOLIC_LINK
                | TreeRefusalCode.SPECIAL_FILE
                | TreeRefusalCode.INVALID_TREE_PATH
                | TreeRefusalCode.NORMALIZATION_COLLISION
                | TreeRefusalCode.PATH_COLLISION
                | TreeRefusalCode.EMPTY_TREE
                | TreeRefusalCode.LONE_FILE_EXCLUDED
                | TreeRefusalCode.GITIGNORE_NOT_UTF8
                | TreeRefusalCode.DUPLICATE_KEY
                | TreeRefusalCode.EXCLUDED_NAME
                | TreeRefusalCode.MALFORMED_ENTRY
                | TreeRefusalCode.MISSING_BLOB
                | TreeRefusalCode.FUNCTION_NAME_WITHOUT_MODULE
                | TreeRefusalCode.FUNCTION_NAME_INVALID_SEGMENT
                | TreeRefusalCode.MODULE_NOT_IN_TREE
                | TreeRefusalCode.MODULE_AMBIGUOUS
            ):
                # Resolving a URL's path refuses it only by the reference codes above.
                return f"Its relative URL names no file of {tree_label}."
