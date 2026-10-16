"""Resolving a file a bundle field names, such as a `PipeDocGen` step's `template_file`, in the bundle's method tree.

The standard's resolution (`mthds/docs/spec/method-tree.md`, "File References") is `mthds-python`'s: the path is
joined to the bundle's own tree path, a `..` may climb as long as it stays inside the tree, and the result must be a
file of the tree, which is a lookup in the set of tree paths the listing produced. So a file the membership rule keeps
out of the tree, a dotfile, a `.gitignore`d file or a file of a nested package, is invisible to the step, and nothing
outside the tree is ever opened.

A bundle loaded from a content string belongs to no tree and reads only the files submitted with it, so the parser,
told so by its caller, validates its blueprint under that origin (`BundleValidationContext`), and a reference none of
those files could be keyed by is refused there, as a blueprint item at the step that names it.
"""

from enum import StrEnum

from mthds.method_tree.exceptions import MethodTreeRefusedError
from mthds.method_tree.references import resolve_reference
from mthds.method_tree.vocabulary import ReferenceContext, TreeRefusalCode
from pydantic import BaseModel, ConfigDict, Field

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.bundle_resources.bundle_resource import resource_path_refusal
from pipelex.core.method_trees.tree_bundle import TreeBundle

ONE_FILE_TREE_ADVICE = "Run the method's folder instead, or add a METHODS.toml to it."


class BundleFileOrigin(StrEnum):
    """Where a bundle's steps find the files they name, which decides the rule a file reference is held to.

    A bundle read from this host's disk finds them in its method tree, where a `..` may climb to another folder of the
    tree. A bundle loaded from a content string belongs to no tree: it reads only the files submitted with it, each
    keyed by a path inside the bundle (`resource_path_refusal`), so a reference no such key could be, one holding a
    `..` segment included, can never be supplied.
    """

    METHOD_TREE = "method_tree"
    SUBMITTED_FILES = "submitted_files"


class BundleValidationContext(BaseModel):
    """The pydantic validation context the parser validates a bundle's blueprint with.

    The validators that check a file reference, such as a `PipeDocGen` step's `template_file`, read it to know which
    rule the reference is held to.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    file_origin: BundleFileOrigin = Field(strict=False)


def bundle_file_origin(*, validation_context: object) -> BundleFileOrigin:
    """Where the bundle under validation finds the files its steps name, as its validation context says.

    A blueprint validated with no such context, such as one a loader parsed from its path, a crate's blueprint loaded
    again or one built in code, is held to the method tree's rule, which checks a reference's form alone: its load then
    resolves the reference in the bundle's tree, or, for a bundle in none, refuses a file not submitted with it.
    """
    if isinstance(validation_context, BundleValidationContext):
        return validation_context.file_origin
    return BundleFileOrigin.METHOD_TREE


def file_reference_refusal(*, reference: str, file_origin: BundleFileOrigin) -> str | None:
    """Why a path written in a bundle field cannot name a file where the bundle finds its files, or None when it can.

    The form check comes first, whatever the origin. A bundle reading its files from its method tree is held to it
    alone, its load deciding in the tree whether the path names a file. A bundle reading only the files submitted with
    it is also held to the rule those files are keyed by, so a step naming a file that could never be submitted, such
    as one through a `..` segment, is refused when its blueprint validates, before any file is looked up. The reason
    never repeats the path.
    """
    form_refusal = file_reference_form_refusal(reference=reference)
    if form_refusal is not None:
        return form_refusal
    match file_origin:
        case BundleFileOrigin.METHOD_TREE:
            return None
        case BundleFileOrigin.SUBMITTED_FILES:
            return resource_path_refusal(path=reference)


def file_reference_form_refusal(*, reference: str) -> str | None:
    """Why a path written in a bundle field cannot name a file of any method tree, or None when its form can.

    The checks a blueprint can make on its own, before any tree is at hand: the standard's form check in path
    context. Whether the path names a file is decided when the bundle loads, in its tree. A `..` segment passes here:
    it may climb to a file elsewhere in the tree. The reason never repeats the path, which a host library's step would
    otherwise put in front of a caller.
    """
    if not reference.strip():
        return "it is empty"
    if "://" in reference:
        return "it is a URL; write a path relative to the bundle's file"
    if reference.startswith("/"):
        return "it is absolute; write it relative to the bundle's file"
    if "\\" in reference:
        return "it holds a backslash; write the path with forward slashes"
    # No tree path holds a colon, so a reference holding one, such as a drive letter or a scheme, names no file.
    if ":" in reference:
        return "it holds a colon, which no file of a method tree can"
    return None


def resolve_bundle_file_reference(*, reference: str, tree_bundle: TreeBundle) -> str:
    """The tree path of the file a bundle field names, resolved against the bundle's tree path in its method tree.

    Raises:
        MethodTreeRefusedError: When the reference is refused; `refusal.code` says at which step of the resolution,
            and `reference_refusal_reason` words it for the bundle's author.
    """
    resolved = resolve_reference(reference, holder=tree_bundle.tree_path, context=ReferenceContext.PATH, tree=tree_bundle.tree)
    if resolved is None:
        msg = f"A reference in path context is always a file reference, yet '{reference}' was resolved as none."
        raise PipelexUnexpectedError(msg)
    return resolved


def reference_refusal_reason(*, refusal_error: MethodTreeRefusedError, tree_bundle: TreeBundle) -> str:
    """Why a file reference was refused, as a sentence naming files by their tree paths only, never by a host path.

    The refusal of a reference from a one-file tree, the tree of a `.mthds` file named alone with no `METHODS.toml`
    at or above it, says how to give the bundle the files beside it. Every other refusal is `mthds-python`'s own
    wording, which names the reference and the bundle by tree path.
    """
    match refusal_error.refusal.code:
        case TreeRefusalCode.REFERENCE_IN_ONE_FILE_TREE:
            references = ", ".join(f"'{name}'" for name in refusal_error.refusal.names)
            return (
                f"The file reference {references} in '{tree_bundle.tree_path}' names a file beside the bundle, which its method does not hold: "
                f"'{tree_bundle.tree_path}' was run alone, with no METHODS.toml at or above its folder, so its method is that one file. "
                f"{ONE_FILE_TREE_ADVICE}"
            )
        case (
            TreeRefusalCode.REFERENCE_INVALID
            | TreeRefusalCode.REFERENCE_LEAVES_TREE
            | TreeRefusalCode.REFERENCE_NOT_A_TREE_PATH
            | TreeRefusalCode.REFERENCE_NOT_IN_TREE
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
            return refusal_error.message
