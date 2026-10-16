"""Which pipe a method starts at when a run of its folder names none.

The rule is the MTHDS protocol's for a request that names no `pipe_code` (`mthds/docs/spec/protocol.md`): a method
tree has no order, so no bundle is "the first" any more. The run starts at the manifest's `main_pipe` when the tree
holds a `METHODS.toml` at its root, or else, in a method with no manifest, at the one `main_pipe` its bundles declare.
A manifest declaring no `main_pipe`, or a method with no manifest whose bundles declare none or several, is refused,
with the bundles named by their tree paths.

`select_entry` applies the rule to bundles already parsed, wherever their tree was read from; `select_method_entry`
reads a tree listed from this host's disk.
"""

from typing import NamedTuple

from mthds.method_tree.discovery import MANIFEST_NAME
from mthds.method_tree.models import MethodTree
from mthds.package.discovery import read_package_manifest_at
from mthds.package.exceptions import ManifestError
from mthds.package.manifest.schema import MethodsManifest

from pipelex.base_exceptions import PipelexUnexpectedError
from pipelex.libraries.method_trees import tree_bundles_of
from pipelex.mthds_parsing.parser import MthdsParser
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.pipe_machinery.pipe_factory import PipeFactory
from pipelex.pipeline.exceptions import MethodEntryError


class EntryCandidate(NamedTuple):
    """A bundle of the method, named by its tree path, as its text declares it."""

    tree_path: str
    blueprint: PipelexBundleBlueprint


class MethodEntry(NamedTuple):
    """The pipe a run of a method starts at, and the tree path of the bundle that defines it."""

    tree_path: str
    pipe_code: str
    pipe_ref: str


def _listed(*, names: list[str]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def _entry_of(*, candidate: EntryCandidate, pipe_code: str) -> MethodEntry:
    return MethodEntry(
        tree_path=candidate.tree_path,
        pipe_code=pipe_code,
        pipe_ref=PipeFactory.make_pipe_ref_with_domain(domain_code=candidate.blueprint.domain, pipe_code=pipe_code),
    )


def select_entry(*, candidates: list[EntryCandidate], manifest: MethodsManifest | None, method_label: str) -> MethodEntry:
    """The pipe a run of a method starts at when it names none, by the MTHDS protocol's rule.

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
        raise MethodEntryError(msg)
    if manifest is not None:
        return _manifest_entry(candidates=candidates, manifest=manifest, method_label=method_label, bundle_paths=bundle_paths)

    declaring = [candidate for candidate in candidates if candidate.blueprint.main_pipe]
    if not declaring:
        msg = (
            f"The method {method_label} has no {MANIFEST_NAME}, and none of its bundles declares a main_pipe "
            f"({_listed(names=bundle_paths)}), so it has no pipe to start at. Declare a main_pipe in one bundle, or name the pipe to run."
        )
        raise MethodEntryError(msg)
    if len(declaring) > 1:
        declarations = ", ".join(f"'{candidate.tree_path}' declares '{candidate.blueprint.main_pipe}'" for candidate in declaring)
        msg = (
            f"The method {method_label} has no {MANIFEST_NAME}, and several of its bundles declare a main_pipe: {declarations}. "
            f"A method starts at one pipe: keep one main_pipe, declare the method's main_pipe in a {MANIFEST_NAME} at its root, "
            "or name the pipe to run."
        )
        raise MethodEntryError(msg)
    entry_candidate = declaring[0]
    main_pipe = entry_candidate.blueprint.main_pipe
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
        raise MethodEntryError(msg)
    # The manifest refuses a main_pipe no domain exports, so the domains exporting it say which bundles may define it.
    exporting_domains = {domain for domain, domain_exports in manifest.exports.items() if main_pipe in domain_exports.pipes}
    defining = [
        candidate
        for candidate in candidates
        if candidate.blueprint.domain in exporting_domains and candidate.blueprint.pipe is not None and main_pipe in candidate.blueprint.pipe
    ]
    if not defining:
        msg = (
            f"The {MANIFEST_NAME} of the method {method_label} declares the main_pipe '{main_pipe}', exported by "
            f"{_listed(names=sorted(exporting_domains))}, which none of its bundles defines in that domain: {_listed(names=bundle_paths)}."
        )
        raise MethodEntryError(msg)
    if len(defining) > 1:
        definitions = ", ".join(f"'{candidate.tree_path}' in domain '{candidate.blueprint.domain}'" for candidate in defining)
        msg = (
            f"The {MANIFEST_NAME} of the method {method_label} declares the main_pipe '{main_pipe}', which several of its "
            f"bundles define: {definitions}. Name the pipe to run as domain.pipe_code."
        )
        raise MethodEntryError(msg)
    return _entry_of(candidate=defining[0], pipe_code=main_pipe)


def select_method_entry(*, tree: MethodTree) -> MethodEntry:
    """The pipe a run of a method tree listed from this host's disk starts at when it names none.

    Each bundle of the tree is parsed to read what it declares, and the manifest at the tree's root, when the tree
    holds one, is read.

    Raises:
        MethodEntryError: The tree has no directory on this host, its manifest cannot be read, or `select_entry`
            refuses it.
        MthdsParserError: A bundle of the tree does not parse.
    """
    if tree.directory is None:
        msg = "A method tree read from a map of file entries has no folder on this host to read its bundles from."
        raise MethodEntryError(msg)
    method_label = f"at '{tree.directory}'"
    candidates = [
        EntryCandidate(tree_path=tree_bundle.tree_path, blueprint=MthdsParser.make_pipelex_bundle_blueprint(bundle_path=tree_bundle.location))
        for tree_bundle in tree_bundles_of(tree=tree)
    ]
    manifest: MethodsManifest | None = None
    if MANIFEST_NAME in tree.members:
        try:
            manifest = read_package_manifest_at(tree.directory)
        except ManifestError as exc:
            msg = f"The {MANIFEST_NAME} of the method {method_label} cannot be read: {exc}"
            raise MethodEntryError(msg) from exc
        if manifest is None:
            msg = f"The method {method_label} lists a {MANIFEST_NAME} at its root that could not be read back."
            raise MethodEntryError(msg)
    return select_entry(candidates=candidates, manifest=manifest, method_label=method_label)
