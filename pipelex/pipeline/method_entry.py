"""Which pipe a method starts at when a command handed its folder names none.

The rule is the MTHDS protocol's for a request that names no `pipe_code` (`mthds/docs/spec/protocol.md`): a method
tree has no order, so no bundle is "the first" any more. The method starts at the manifest's `main_pipe` when the tree
holds a `METHODS.toml` at its root, or else, in a method with no manifest, at the one `main_pipe` its bundles declare.
A manifest declaring no `main_pipe`, or a method with no manifest whose bundles declare none or several, is refused,
with the bundles named by their tree paths.

The rule reads what each bundle declares of where its method starts, its `domain`, its `main_pipe` and the codes of its
pipes, and nothing else: a bundle whose pipes do not validate still says where its method starts, and is refused when
the method loads, by the command that loads it. Only a bundle whose declarations cannot be read, such as one that is
not TOML, is refused here.

`select_entry` applies the rule to bundles already read, wherever their tree was read from; `select_method_entry`
reads a tree listed from this host's disk. `select_named_pipe` finds the bundle defining a pipe the caller named, for a
command that acts on a bundle of the method rather than on the method's whole library.
"""

from pathlib import Path
from typing import Any, NamedTuple, Self, cast

from mthds.method_tree.discovery import BUNDLE_SUFFIX, MANIFEST_NAME
from mthds.method_tree.models import MethodTree
from mthds.package.discovery import read_package_manifest_at
from mthds.package.exceptions import ManifestError
from mthds.package.manifest.schema import MethodsManifest
from mthds.protocol.problem.registry import CoreCode

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.libraries.pipe.pipe_suggestions import MAIN_PIPE_DECLARATION, close_pipe_refs
from pipelex.methods.package_reason import MethodPackageReason
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.validation import is_pipe_code_valid
from pipelex.pipeline.exceptions import MethodEntryError
from pipelex.tools.misc.exceptions import TomlError
from pipelex.tools.misc.toml_utils import load_toml_from_path

_DOMAIN_KEY = "domain"
_MAIN_PIPE_KEY = "main_pipe"
_PIPE_KEY = "pipe"


class EntryCandidate(NamedTuple):
    """A bundle of the method, named by its tree path, by what it declares of where its method starts."""

    tree_path: str
    domain: str
    main_pipe: str | None
    pipe_codes: frozenset[str]

    @classmethod
    def of_blueprint(cls, *, tree_path: str, blueprint: PipelexBundleBlueprint) -> Self:
        """The candidate a parsed bundle makes."""
        return cls(
            tree_path=tree_path,
            domain=blueprint.domain,
            main_pipe=blueprint.main_pipe,
            pipe_codes=frozenset(blueprint.pipe or {}),
        )


class MethodEntry(NamedTuple):
    """The pipe a command acts on, and the tree path of the bundle that defines it."""

    tree_path: str
    pipe_code: str
    pipe_ref: str


def _listed(*, names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def _declared_pipe_refs(*, candidates: list[EntryCandidate]) -> list[str]:
    """The qualified refs of every pipe the method's bundles declare, sorted: the pipes a run may name to start at."""
    return sorted({f"{candidate.domain}.{pipe_code}" for candidate in candidates for pipe_code in candidate.pipe_codes})


def _entry_of(*, candidate: EntryCandidate, pipe_code: str) -> MethodEntry:
    return MethodEntry(
        tree_path=candidate.tree_path,
        pipe_code=pipe_code,
        pipe_ref=QualifiedRef.from_domain_and_code(domain_path=candidate.domain, local_code=pipe_code).full_ref,
    )


def _declared_candidate(*, tree_path: str, bundle_dict: dict[str, Any]) -> EntryCandidate | None:
    """The candidate a bundle's raw TOML declares, or None when the full parse must say what is wrong with it.

    That is when its domain or pipe table has the wrong type, or its main_pipe is not a pipe code: a `main_pipe` is
    held to the rule the bundle's parse holds it to, so `dom.pipe`, `camelCase` and an empty string are refused as the
    load would refuse them, never read as a pipe to start at nor, for the empty string, as declaring none.
    """
    domain = bundle_dict.get(_DOMAIN_KEY)
    main_pipe = bundle_dict.get(_MAIN_PIPE_KEY)
    pipe_table = bundle_dict.get(_PIPE_KEY)
    if not isinstance(domain, str):
        return None
    if main_pipe is not None and not (isinstance(main_pipe, str) and is_pipe_code_valid(main_pipe)):
        return None
    if pipe_table is not None and not isinstance(pipe_table, dict):
        return None
    pipe_codes = frozenset(cast("dict[str, Any]", pipe_table or {}))
    return EntryCandidate(tree_path=tree_path, domain=domain, main_pipe=main_pipe, pipe_codes=pipe_codes)


def read_entry_candidate(*, tree_path: str, bundle_file: Path) -> EntryCandidate:
    """What a bundle file declares of where its method starts, read without validating its pipes.

    Raises:
        MthdsParserError: The bundle is not TOML or not UTF-8 text, its domain or pipe table cannot be read, or its
            main_pipe is not a valid pipe code, each located as its full parse locates it.
    """
    try:
        bundle_dict = load_toml_from_path(path=bundle_file)
    except (TomlError, UnicodeDecodeError):
        candidate = None
    else:
        candidate = _declared_candidate(tree_path=tree_path, bundle_dict=bundle_dict)
    if candidate is not None:
        return candidate
    # What the bundle declares cannot be read as it stands: its full parse says why, as the load would.
    blueprint = MthdsParser.make_pipelex_bundle_blueprint(bundle_path=bundle_file)
    return EntryCandidate.of_blueprint(tree_path=tree_path, blueprint=blueprint)


def tree_method_label(*, tree: MethodTree) -> str:
    """How the entry rule's messages name a method tree listed from this host's disk: by its folder."""
    return f"at '{tree.directory}'"


def read_method_candidates(*, tree: MethodTree) -> list[EntryCandidate]:
    """The bundles of a method tree listed from this host's disk, in tree path order, by what each declares.

    Raises:
        PipelexUnexpectedError: The tree has no directory on this host to read its bundles from, which is a host's
            wiring bug.
        MthdsParserError: A bundle's declarations cannot be read (see `read_entry_candidate`).
    """
    if tree.directory is None:
        # A host handing an in-memory tree to the reader of trees on disk: a wiring bug of ours, never the caller's method.
        msg = "A method tree read from a map of file entries has no folder on this host to read its bundles from."
        raise PipelexUnexpectedError(msg)
    return [
        read_entry_candidate(tree_path=tree_path, bundle_file=tree.file_location(tree_path))
        for tree_path in tree.tree_paths
        if tree_path.endswith(BUNDLE_SUFFIX)
    ]


def read_method_manifest(*, tree: MethodTree) -> MethodsManifest | None:
    """The `METHODS.toml` at the root of a method tree listed from this host's disk, or None when it holds none there.

    Raises:
        MethodEntryError: Its manifest cannot be read.
        PipelexUnexpectedError: The tree has no directory on this host, which is a host's wiring bug.
    """
    if MANIFEST_NAME not in tree.members:
        return None
    if tree.directory is None:
        # A host handing an in-memory tree to the reader of trees on disk: a wiring bug of ours, never the caller's method.
        msg = "A method tree read from a map of file entries has no folder on this host to read its manifest from."
        raise PipelexUnexpectedError(msg)
    method_label = tree_method_label(tree=tree)
    try:
        manifest = read_package_manifest_at(tree.directory)
    except ManifestError as exc:
        msg = f"The {MANIFEST_NAME} of the method {method_label} cannot be read: {exc}"
        raise (
            MethodEntryError(msg)
            .with_error_code(CoreCode.METHOD_PACKAGE_INVALID)
            .with_params(reason=MethodPackageReason.MANIFEST_INVALID, path=MANIFEST_NAME)
        ) from exc
    if manifest is None:
        msg = f"The method {method_label} lists a {MANIFEST_NAME} at its root that could not be read back."
        raise (
            MethodEntryError(msg)
            .with_error_code(CoreCode.METHOD_PACKAGE_INVALID)
            .with_params(reason=MethodPackageReason.MANIFEST_INVALID, path=MANIFEST_NAME)
        )
    return manifest


def select_entry(*, candidates: list[EntryCandidate], manifest: MethodsManifest | None, method_label: str) -> MethodEntry:
    """The pipe a method starts at when the caller names none, by the MTHDS protocol's rule.

    Args:
        candidates: The method's bundles, in tree path order.
        manifest: The `METHODS.toml` at the tree's root, or None when the tree holds none there.
        method_label: How the messages name the method, such as its folder.

    Raises:
        MethodEntryError: The method holds no bundle, its manifest declares no `main_pipe` or one no single bundle
            defines, or, with no manifest, its bundles declare none or several.
    """
    bundle_paths = [candidate.tree_path for candidate in candidates]
    if not candidates:
        msg = f"The method {method_label} holds no .mthds bundle, so it has no pipe to start at."
        raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_INVALID)
    if manifest is not None:
        return _manifest_entry(candidates=candidates, manifest=manifest, method_label=method_label, bundle_paths=bundle_paths)

    declaring = [candidate for candidate in candidates if candidate.main_pipe is not None]
    if not declaring:
        msg = (
            f"The method {method_label} has no {MANIFEST_NAME}, and none of its bundles declares a main_pipe "
            f"({_listed(names=bundle_paths)}), so it has no pipe to start at. Declare a main_pipe in one bundle, or name the pipe to run."
        )
        raise MethodEntryError(msg).with_params(candidates=_declared_pipe_refs(candidates=candidates))
    if len(declaring) > 1:
        declarations = ", ".join(f"'{candidate.tree_path}' declares '{candidate.main_pipe}'" for candidate in declaring)
        msg = (
            f"The method {method_label} has no {MANIFEST_NAME}, and several of its bundles declare a main_pipe: {declarations}. "
            f"A method starts at one pipe: keep one main_pipe, declare the method's main_pipe in a {MANIFEST_NAME} at its root, "
            "or name the pipe to run."
        )
        # The run names no pipe, so there is no selector for `request.pipe_ambiguous` to name: the pipes it may name are
        # the candidates of the default code, `request.pipe_unspecified`.
        declared_refs = sorted(f"{candidate.domain}.{candidate.main_pipe}" for candidate in declaring)
        raise MethodEntryError(msg).with_params(candidates=declared_refs)
    entry_candidate = declaring[0]
    main_pipe = entry_candidate.main_pipe
    if main_pipe is None:
        # Selected because it declares one: this is a bug of the selection, never the caller's method.
        msg = f"The bundle '{entry_candidate.tree_path}' was selected for its main_pipe, yet declares none."
        raise PipelexUnexpectedError(msg)
    return _entry_of(candidate=entry_candidate, pipe_code=main_pipe)


def _manifest_entry(*, candidates: list[EntryCandidate], manifest: MethodsManifest, method_label: str, bundle_paths: list[str]) -> MethodEntry:
    """The pipe the manifest names as its `main_pipe`, in the one bundle of a domain exporting it that defines it.

    Raises:
        MethodEntryError: The manifest declares no `main_pipe`, or none or several bundles define it.
    """
    main_pipe = manifest.main_pipe
    if main_pipe is None:
        msg = (
            f"The {MANIFEST_NAME} of the method {method_label} declares no main_pipe, so the method has no pipe to start at. "
            f"Declare main_pipe under [package], or name the pipe to run. Its bundles: {_listed(names=bundle_paths)}."
        )
        raise MethodEntryError(msg).with_params(candidates=_declared_pipe_refs(candidates=candidates))
    # The manifest refuses a main_pipe no domain exports, so the domains exporting it say which bundles may define it.
    exporting_domains = {domain for domain, domain_exports in manifest.exports.items() if main_pipe in domain_exports.pipes}
    defining = [candidate for candidate in candidates if candidate.domain in exporting_domains and main_pipe in candidate.pipe_codes]
    if not defining:
        msg = (
            f"The {MANIFEST_NAME} of the method {method_label} declares the main_pipe '{main_pipe}', exported by "
            f"{_listed(names=sorted(exporting_domains))}, which none of its bundles defines in that domain: {_listed(names=bundle_paths)}."
        )
        raise (
            MethodEntryError(msg)
            .with_error_code(CoreCode.METHOD_PIPE_UNRESOLVED)
            .with_params(
                pipe=MAIN_PIPE_DECLARATION,
                missing=main_pipe,
                candidates=close_pipe_refs(name=main_pipe, pipe_refs=_declared_pipe_refs(candidates=candidates)),
            )
        )
    if len(defining) > 1:
        definitions = ", ".join(f"'{candidate.tree_path}' in domain '{candidate.domain}'" for candidate in defining)
        msg = (
            f"The {MANIFEST_NAME} of the method {method_label} declares the main_pipe '{main_pipe}', which several of its "
            f"bundles define: {definitions}. Name the pipe to run as domain.pipe_code."
        )
        # The manifest's own declaration matches several pipes, which its author resolves: never a pipe that does not exist.
        defined_refs = sorted(f"{candidate.domain}.{main_pipe}" for candidate in defining)
        raise MethodEntryError(msg).with_error_code(CoreCode.METHOD_REF_AMBIGUOUS).with_params(ref=main_pipe, candidates=defined_refs)
    return _entry_of(candidate=defining[0], pipe_code=main_pipe)


def select_method_entry(*, tree: MethodTree) -> MethodEntry:
    """The pipe a method tree listed from this host's disk starts at when the caller names none.

    Each bundle of the tree is read for what it declares, and the manifest at the tree's root, when the tree holds one,
    is read.

    Raises:
        MethodEntryError: Its manifest cannot be read, or `select_entry` refuses it.
        PipelexUnexpectedError: The tree has no directory on this host, which is a host's wiring bug.
        MthdsParserError: A bundle's declarations cannot be read (see `read_entry_candidate`).
    """
    candidates = read_method_candidates(tree=tree)
    manifest = read_method_manifest(tree=tree)
    return select_entry(candidates=candidates, manifest=manifest, method_label=tree_method_label(tree=tree))


def select_named_pipe(*, candidates: list[EntryCandidate], pipe_ref: str, method_label: str) -> MethodEntry:
    """The bundle of a method defining the pipe the caller named, as `pipe_code` or `domain.pipe_code`.

    Raises:
        MethodEntryError: The name is a dependency's pipe or not a pipe reference, no bundle of the method defines the
            pipe, or, named by its bare code, bundles of several domains define it.
    """
    bundle_paths = [candidate.tree_path for candidate in candidates]
    if QualifiedRef.has_cross_package_prefix(pipe_ref):
        msg = (
            f"The pipe '{pipe_ref}' belongs to a package the method {method_label} depends on, and no bundle of the method "
            "defines it. Name a pipe of the method, or the bundle file that runs it."
        )
        raise MethodEntryError(msg).with_error_code(CoreCode.REQUEST_PIPE_NOT_FOUND).with_params(pipe=pipe_ref)
    try:
        qualified_ref = QualifiedRef.parse(pipe_ref)
    except QualifiedRefError as exc:
        msg = f"'{pipe_ref}' does not name a pipe of the method {method_label}: {exc}"
        raise MethodEntryError(msg).with_error_code(CoreCode.REQUEST_PIPE_NOT_FOUND).with_params(pipe=pipe_ref) from exc
    defining = [
        candidate
        for candidate in candidates
        if qualified_ref.local_code in candidate.pipe_codes and (qualified_ref.domain_path is None or candidate.domain == qualified_ref.domain_path)
    ]
    if not defining:
        msg = f"No bundle of the method {method_label} defines the pipe '{pipe_ref}'. Its bundles: {_listed(names=bundle_paths)}."
        suggestions = close_pipe_refs(name=pipe_ref, pipe_refs=_declared_pipe_refs(candidates=candidates))
        raise MethodEntryError(msg).with_error_code(CoreCode.REQUEST_PIPE_NOT_FOUND).with_params(pipe=pipe_ref, suggestions=suggestions)
    if len(defining) > 1:
        definitions = ", ".join(f"'{candidate.tree_path}' in domain '{candidate.domain}'" for candidate in defining)
        msg = f"Several bundles of the method {method_label} define the pipe '{pipe_ref}': {definitions}. Name the pipe as domain.pipe_code."
        defined_refs = sorted(f"{candidate.domain}.{qualified_ref.local_code}" for candidate in defining)
        raise MethodEntryError(msg).with_error_code(CoreCode.REQUEST_PIPE_AMBIGUOUS).with_params(pipe=pipe_ref, candidates=defined_refs)
    return _entry_of(candidate=defining[0], pipe_code=qualified_ref.local_code)
