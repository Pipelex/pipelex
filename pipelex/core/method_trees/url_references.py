"""Resolving a relative URL of a template, a file reference in URL context, in the set of its method tree's paths.

A relative URL in an HTML template, such as an image's `src` or a stylesheet's `href`, names a file of the template's
own method tree, resolved against the directory of the file that holds it by the MTHDS standard's steps
(`mthds/docs/spec/method-tree.md`, "File References"): take the URL's path, dropping its fragment and then its query;
check its form; split it at each `/` and percent-decode each segment; normalize it to NFC; join it to the holder's
directory and resolve its `.` and `..` segments lexically; check the result is a tree path; look it up. The first step
that fails decides the refusal. A URL naming a scheme, holding an authority or with no path is no file reference: it is
left exactly as written, never resolved and never refused.

`mthds-python` implements these steps as `resolve_reference`, for a tree listed from a directory or read from a map of
file entries, whose holder is a file of the tree. The print of a document knows less than that, and resolves more:

- **A listing.** The print reads the tree through the method file store, whose listing names each file's hash and tree
  path, and nothing else of where the tree came from, so a reference is looked up in a set of tree paths.
- **A holder at the root.** Bundles parsed from content strings sit at the root of the tree of the files submitted with
  them without being a file of it, and the path below the root of a URL an engine joined to the print's base URL is a
  path from the root (`pipelex.cogt.doc_gen.method_file_urls`): both resolve from the root.

So the steps are run here, over a set of tree paths, with `mthds-python`'s own pieces for each of them but the URL
path's percent-decoding, which it keeps private and which is written again below to the same rules. A test holds this
module to `resolve_reference`'s answers for every reference a holder of the tree writes.

Resolving a reference is a lookup in the tree's set of paths, never a file system access: nothing here opens a path.
"""

import re
import unicodedata
from collections.abc import Set as AbstractSet
from urllib.parse import unquote

from mthds.method_tree.exceptions import MethodTreeRefusedError, TreeRefusal
from mthds.method_tree.references import ROOT_RESOLVED, is_file_reference, lexical_join
from mthds.method_tree.tree_path import CONTROL_CATEGORY, nfc, tree_path_violation
from mthds.method_tree.vocabulary import ReferenceContext, TreeRefusalCode

#: A `%` not followed by two hexadecimal digits, which makes a URL's path malformed.
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
#: The holder a path is joined to when it resolves from the root: any lone segment, since a join keeps the holder's
#: directories and drops its name.
_ROOT_HOLDER = "."


def url_path_of(*, reference: str) -> str:
    """A URL's path as written: what is left once its fragment, then its query, are dropped.

    `urllib.parse.urlsplit` is not used: it silently drops tabs and line breaks, which the standard keeps so that the
    result check can refuse them.
    """
    return reference.split("#", 1)[0].split("?", 1)[0]


def resolve_url_reference(*, reference: str, holder: str | None, tree_paths: AbstractSet[str], holder_label: str | None = None) -> str | None:
    """The tree path of the file a relative URL written in `holder` names, by the standard's steps in URL context.

    Args:
        reference: The URL exactly as written.
        holder: The tree path of the file holding the URL, or None for a URL that resolves from the root.
        tree_paths: The tree paths of the tree's files.
        holder_label: How a refusal names the holder, such as "the template file 'templates/letter.html'"; its tree
            path when None.

    Returns:
        The tree path the URL names, or None for a URL that is no file reference, such as `https://…`, `data:…`,
        `//host/x` or `#top`, which the caller leaves exactly as written.

    Raises:
        MethodTreeRefusedError: The URL is refused; `refusal.code` says at which step, and `refusal.resolved` holds what
            it resolved to from the join on.
    """
    if not is_file_reference(reference, context=ReferenceContext.URL):
        return None
    return resolve_url_path(
        url_path=url_path_of(reference=reference), reference=reference, holder=holder, tree_paths=tree_paths, holder_label=holder_label
    )


def resolve_url_path(*, url_path: str, reference: str, holder: str | None, tree_paths: AbstractSet[str], holder_label: str | None = None) -> str:
    """The tree path a URL's path names from `holder`, its query and fragment already dropped: steps 2 to 7.

    A URL's path is always a file reference, whatever it looks like, so it is resolved without first asking whether it
    names a scheme: an engine that joined a URL to the print's base URL has already told a reference from an absolute
    URL, and what is left below the root may hold a colon, which the result check refuses.

    Args:
        url_path: The URL's path, as written or as an engine joined it.
        reference: How a refusal names the URL.
        holder: The tree path of the file holding the URL, or None for a path that resolves from the root.
        tree_paths: The tree paths of the tree's files.
        holder_label: How a refusal names the holder; its tree path when None.

    Raises:
        MethodTreeRefusedError: The path is refused, `refusal.code` saying at which step.
    """
    if holder_label is None:
        holder_label = f"'{holder}'" if holder is not None else "the root of its method tree"
    if url_path.startswith("/") or "\\" in url_path:
        raise _refusal(
            reference=reference,
            holder_label=holder_label,
            code=TreeRefusalCode.REFERENCE_INVALID,
            explanation="starts with '/' or holds a backslash.",
        )
    decoded = nfc(_percent_decoded(url_path=url_path, reference=reference, holder_label=holder_label))
    segments = lexical_join(holder=holder or _ROOT_HOLDER, path=decoded)
    if segments is None:
        explanation = "climbs above the root of its method tree."
        raise _refusal(reference=reference, holder_label=holder_label, code=TreeRefusalCode.REFERENCE_LEAVES_TREE, explanation=explanation)
    # The root itself, with no segment or with only a trailing '/', passes the result check and is refused at the lookup.
    is_root = segments in ([], [""])
    resolved = ROOT_RESOLVED if is_root else "/".join(segments)
    if not is_root:
        violation = tree_path_violation(resolved)
        if violation is not None:
            explanation = f"resolves to '{resolved}', which is not a tree path: {violation}."
            raise _refusal(
                reference=reference,
                holder_label=holder_label,
                code=TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH,
                explanation=explanation,
                resolved=resolved,
            )
    if resolved in tree_paths:
        return resolved
    what = "the root of the tree, not a file" if is_root else f"'{resolved}', which is not a file of the tree"
    explanation = f"resolves to {what}."
    raise _refusal(
        reference=reference, holder_label=holder_label, code=TreeRefusalCode.REFERENCE_NOT_IN_TREE, explanation=explanation, resolved=resolved
    )


def _percent_decoded(*, url_path: str, reference: str, holder_label: str) -> str:
    """Step 3: the path split at each `/`, each segment percent-decoded, so decoding never creates a separator.

    Raises:
        MethodTreeRefusedError: A segment holds a `%` not followed by two hexadecimal digits, or decodes to bytes that
            are not UTF-8, to a `/`, a backslash or a control character.
    """
    decoded_segments: list[str] = []
    for segment in url_path.split("/"):
        if _MALFORMED_PERCENT_ESCAPE.search(segment):
            explanation = "holds a '%' not followed by two hexadecimal digits; write a literal '%' as '%25'."
            raise _refusal(reference=reference, holder_label=holder_label, code=TreeRefusalCode.REFERENCE_INVALID, explanation=explanation)
        try:
            decoded_segment = unquote(segment, encoding="utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            explanation = "percent-decodes to bytes that are not UTF-8."
            raise _refusal(reference=reference, holder_label=holder_label, code=TreeRefusalCode.REFERENCE_INVALID, explanation=explanation) from exc
        if "/" in decoded_segment or "\\" in decoded_segment or _control_count(text=decoded_segment) > _control_count(text=segment):
            explanation = "percent-decodes to a '/', a backslash or a control character, which no segment may hold."
            raise _refusal(reference=reference, holder_label=holder_label, code=TreeRefusalCode.REFERENCE_INVALID, explanation=explanation)
        decoded_segments.append(decoded_segment)
    return "/".join(decoded_segments)


def _control_count(*, text: str) -> int:
    return sum(1 for character in text if unicodedata.category(character) == CONTROL_CATEGORY)


def _refusal(*, reference: str, holder_label: str, code: TreeRefusalCode, explanation: str, resolved: str | None = None) -> MethodTreeRefusedError:
    msg = f"The relative URL '{reference}' in {holder_label} {explanation}"
    return MethodTreeRefusedError(msg, refusal=TreeRefusal(code=code, names=[reference], resolved=resolved))
