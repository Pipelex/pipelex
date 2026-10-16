"""Where a relative URL of an HTML document resolves: a file of its template's method tree, named by a URL no network serves.

An HTML template names the files beside it in its method tree by relative URLs: an image's `src`, a stylesheet's `href`,
and the fonts and images a stylesheet names with `url()`. Each is a file reference in URL context, resolved against the
tree path of the file that holds it, by `mthds-python`'s `resolve_reference_in_paths` over the tree's listing, which
resolves one written in no file of the tree from the root. An engine resolves a relative URL as
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
up. The steps first ask whether a URL is a file reference at all, and a path below the root that is empty names the root,
while one that reads as a scheme (`a:b.png`) or an authority (`//x`) is refused here as malformed, as the standard's form
check refuses a path naming a scheme or starting with `/`: what an engine joined is a path whatever it reads as, never a
URL to leave as written. A relative URL an engine hands as written, without joining it, is resolved against the holder by
the same steps. Either way, a refusal is worded here from its code, naming the template, rather than in `mthds-python`'s
words, which name the holder by its tree path alone.

An engine's join applies RFC 3986's removal of dot segments, which parts from the standard's lexical resolution in a few
corner spellings: Python's `urljoin`, which WeasyPrint uses, drops an empty segment, so `a//b` names `a/b` where the
standard refuses it, and turns a trailing `/.` into `/`, so `logo.png/.` is refused where the standard resolves it. None
of these reaches a file outside the tree, since whatever the engine joined, the print reads only a file the tree's listing
names. A URL that climbs out of the tree and back in through the digest's segment resolves inside the tree as well, and
the template's author cannot write one: the digest is that of a tree holding the template itself.

Only the kinds of file a printed document is made of are read: images, stylesheets and fonts, told by their suffix
(`TEMPLATE_ASSET_SUFFIXES`). A relative URL may come from a run's input, interpolated into the template, and a document
can carry what it reads, an attachment for one, so a URL naming any other file of the method, its Python, its bundles or
its data, is refused: a caller allowed to run a method is not thereby allowed to read its files.

Only a relative reference names a file of the tree. A root-absolute path, such as `/tmp/photo.png`, is no relative
reference: an engine joining it to the base URL lands outside the tree's segment, and an engine handing it as written has
it read as the local path it is, under the run's read scope, as any other URI.
"""

from collections.abc import Set as AbstractSet
from pathlib import PurePosixPath
from urllib.parse import quote

from mthds.method_tree.digest import DIGEST_PREFIX
from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeRefusal
from mthds.method_tree.references import ROOT_RESOLVED, is_file_reference, resolve_reference_in_paths, url_path_of
from mthds.method_tree.tree_path import tree_path_violation
from mthds.method_tree.vocabulary import ReferenceContext, TreeRefusalCode
from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.cogt.doc_gen.render_job import METHOD_FILE_URL_PREFIX, is_method_file_url

#: The suffixes of the files a document reads from its method tree, compared without regard to case: images, stylesheets
#: and fonts, the kinds a printed page is made of.
TEMPLATE_ASSET_SUFFIXES: frozenset[str] = frozenset(
    {
        # Images
        ".apng",
        ".avif",
        ".bmp",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".png",
        ".svg",
        ".tif",
        ".tiff",
        ".webp",
        # Stylesheets
        ".css",
        # Fonts
        ".eot",
        ".otf",
        ".ttc",
        ".ttf",
        ".woff",
        ".woff2",
    }
)


def is_relative_url(*, url: str) -> bool:
    """Whether `url` is a relative reference with a path, which in an HTML document names a file of its method tree.

    A URL naming a scheme (`https:`, `data:`, `pipelex-storage:`), one holding an authority (`//host/x`), one with no
    path (`#top`, `?v=2`, the empty URL) and a root-absolute path (`/tmp/photo.png`) are not: each is read as what it
    names, under the run's read scope, or left as written.
    """
    return is_file_reference(url, context=ReferenceContext.URL) and not url.startswith("/")


def template_asset_refusal(*, tree_path: str) -> str | None:
    """Why a document may not read the file of its method tree at `tree_path`, or None for an image, a stylesheet or a font."""
    if PurePosixPath(tree_path).suffix.lower() in TEMPLATE_ASSET_SUFFIXES:
        return None
    return (
        f"It names '{tree_path}', which is not an image, a stylesheet or a font: a document reads only those from its method, "
        "so that a URL a run's input supplies cannot read the method's other files."
    )


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
    is_one_file_tree: bool = Field(
        default=False, description="Whether the tree is the one-file tree of a bundle named alone, which holds no file beside the bundle"
    )

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
            PipelexUnexpectedError: The listing does not hold the holder, so it is not the listing of the template's tree.
        """
        if is_method_file_url(url=url):
            return self._tree_path_of_joined(url=url, tree_paths=tree_paths)
        if self.holder is not None and self.holder not in tree_paths:
            msg = f"The listing a relative URL of {self.template_label} was resolved in does not hold '{self.holder}', the template's own file."
            raise PipelexUnexpectedError(msg)
        try:
            return resolve_reference_in_paths(
                url, holder=self.holder, context=ReferenceContext.URL, tree_paths=tree_paths, is_one_file_tree=self.is_one_file_tree
            )
        except MethodTreeRefusedError as exc:
            msg = self._refusal_message(refusal=exc.refusal, subject=f"The relative URL '{url}'")
            raise MethodTreeRefusedError(msg, refusal=exc.refusal) from exc

    def _tree_path_of_joined(self, *, url: str, tree_paths: AbstractSet[str]) -> str:
        """The tree path a URL an engine joined under the prefix names, resolved from the root below the tree's segment."""
        tree_segment, _separator, below_root = url_path_of(url[len(METHOD_FILE_URL_PREFIX) :]).partition("/")
        if tree_segment.lower() != self._tree_segment:
            # A join removes each `..` it can, so a URL that climbed above the root, or one written from it, lands
            # outside the tree's own segment.
            msg = f"Its relative URL climbs above the root of the method tree of {self.template_label}, or starts with '/'."
            raise MethodTreeRefusedError(msg, refusal=TreeRefusal(code=TreeRefusalCode.REFERENCE_LEAVES_TREE, names=[below_root]))
        try:
            tree_path = resolve_reference_in_paths(
                below_root, holder=None, context=ReferenceContext.URL, tree_paths=tree_paths, is_one_file_tree=self.is_one_file_tree
            )
        except MethodTreeRefusedError as exc:
            msg = self._refusal_message(refusal=exc.refusal, subject="Its relative URL")
            raise MethodTreeRefusedError(msg, refusal=exc.refusal) from exc
        if tree_path is not None:
            return tree_path
        # The steps leave as written a URL that is no file reference, but what an engine joined below the tree's segment
        # is a path from the root whatever it reads as, so it is refused here: an empty one names the root, and one that
        # reads as a scheme or an authority is malformed, as the form check refuses a path naming a scheme or starting with '/'.
        refusal: TreeRefusal
        if below_root:
            refusal = TreeRefusal(code=TreeRefusalCode.REFERENCE_INVALID, names=[below_root])
        else:
            refusal = TreeRefusal(code=TreeRefusalCode.REFERENCE_NOT_IN_TREE, names=[below_root], resolved=ROOT_RESOLVED)
        raise MethodTreeRefusedError(self._refusal_message(refusal=refusal, subject="Its relative URL"), refusal=refusal)

    def _refusal_message(self, *, refusal: TreeRefusal, subject: str) -> str:
        """Why a relative URL of the document names no file of the tree, worded from the refusal's code, naming the template.

        `mthds-python`'s own message names the holder by its tree path alone, and a URL an engine joined by the engine's
        spelling, so the message is written here, naming what the URL resolved to where the code records it.

        Args:
            refusal: The refusal, as the standard's steps recorded it.
            subject: How the message names the URL: as written, or as "Its relative URL" for one an engine joined.
        """
        tree_label = f"the method tree of {self.template_label}"
        match refusal.code:
            case TreeRefusalCode.REFERENCE_INVALID:
                return (
                    f"{subject} is malformed in {tree_label}: its path names a scheme or starts with '/', or it holds a backslash, "
                    "a '%' not followed by two hexadecimal digits, or a percent-escape that decodes to a '/', a backslash, "
                    "a control character or bytes that are not UTF-8."
                )
            case TreeRefusalCode.REFERENCE_LEAVES_TREE:
                return f"{subject} climbs above the root of {tree_label}."
            case TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH:
                violation = tree_path_violation(refusal.resolved) if refusal.resolved is not None else None
                reason = f": {violation}" if violation is not None else ""
                return f"{subject} resolves to '{refusal.resolved}', which cannot name a file of {tree_label}{reason}."
            case TreeRefusalCode.REFERENCE_NOT_IN_TREE:
                if refusal.resolved == ROOT_RESOLVED:
                    return f"{subject} resolves to the root of {tree_label}, which is not a file."
                return f"{subject} resolves to '{refusal.resolved}', which is not a file of {tree_label}."
            case TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE:
                return (
                    f"{subject} names a file beside the bundle of {self.template_label}, but the bundle was named alone with "
                    "no METHODS.toml at or above it, so its tree holds that one file. Hand over the method's directory instead."
                )
            case (
                TreeRefusalCode.SYMBOLIC_LINK
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
                # Resolving a reference refuses it only by the reference codes above.
                return f"{subject} names no file of {tree_label}."
