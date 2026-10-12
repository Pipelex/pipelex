"""The files submitted with bundles loaded from content strings, checked against their steps and moved with their runs.

`pipelex.core.bundle_resources.bundle_resource` says what a bundle resource is. This module holds what the library
layer does with them: refusing a file no step names, and moving the files read only when a step runs to the run's
storage before the run leaves the process, so the crate a remote orchestrator receives carries references rather
than the bytes.
"""

import mimetypes
import re
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath

from pipelex.core.bundle_resources.bundle_resource import BundleResource, BundleResourceReadStage, canonical_resource_path_or_none
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.libraries.library_crate import LibraryCrate
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint
from pipelex.tools.storage.storage_provider_abstract import StorageProviderAbstract

# The run's storage leaf for the files its caller supplied, under which the bundle's files are stored by digest.
BUNDLE_RESOURCES_STORAGE_PREFIX = "assets/bundle"
_UNSAFE_KEY_CHARACTERS = re.compile(r"[^A-Za-z0-9._-]+")


def bundle_resource_reads(*, pipe_blueprints: Iterable[PipeBlueprintUnion]) -> dict[str, BundleResourceReadStage]:
    """The bundle files these pipes read, keyed by canonical path, and when each is first read.

    A path no file inside a bundle can have, such as one with a `..` segment, is left out: no submitted file can
    answer it, and the step that names it is refused when it is built. A file read at load by one step and at run
    by another counts as read at load, which is the stricter way to carry it.
    """
    reads: dict[str, BundleResourceReadStage] = {}
    for pipe_blueprint in pipe_blueprints:
        for named_path, stage in pipe_blueprint.bundle_resource_reads.items():
            canonical_path = canonical_resource_path_or_none(path=named_path)
            if canonical_path is None:
                continue
            if reads.get(canonical_path) != BundleResourceReadStage.LOAD:
                reads[canonical_path] = stage
    return reads


def check_bundle_resources_are_named(*, blueprints: Iterable[PipelexBundleBlueprint], bundle_resources: Mapping[str, BundleResource]) -> None:
    """Refuse a file submitted with the bundles that none of their steps names.

    Raises:
        BundleResourceNotNamedError: a submitted file is named by no step of the bundles.
    """
    if not bundle_resources:
        return
    pipe_blueprints = [pipe_blueprint for blueprint in blueprints for pipe_blueprint in (blueprint.pipe or {}).values()]
    named_paths = set(bundle_resource_reads(pipe_blueprints=pipe_blueprints))
    unnamed_paths = sorted(set(bundle_resources) - named_paths)
    if not unnamed_paths:
        return
    listed = ", ".join(f"'{path}'" for path in unnamed_paths)
    msg = (
        f"The bundle was submitted with files none of its steps names: {listed}. Submit only the files a step reads, "
        "each keyed by the path the step names, such as a PipeDocGen step's 'template_file', relative to the bundle."
    )
    raise BundleResourceNotNamedError(msg)


async def relocate_run_resources(*, crate: LibraryCrate, storage_provider: StorageProviderAbstract, storage_scope: str) -> LibraryCrate:
    """The crate with every file read only when a step runs stored under the run's scope and carried by reference.

    Called before a live run leaves the process, so the job an orchestrator such as Temporal receives carries a
    reference to each office template rather than its bytes, and its print stage reads the bytes back from the
    run's storage under the run's read scope. A file read when the method loads stays inline, since the remote side
    reads it while it loads the crate, where it may do no IO. The files are stored by digest, so a run that submits
    the same file twice stores it once.
    """
    if not crate.bundle_resources:
        return crate
    run_stage_paths = {
        path for path, stage in bundle_resource_reads(pipe_blueprints=crate.pipes.values()).items() if stage == BundleResourceReadStage.RUN
    }
    relocated: dict[str, BundleResource] = {}
    for path, resource in crate.bundle_resources.items():
        if path not in run_stage_paths or not resource.is_inline:
            relocated[path] = resource
            continue
        file_name = _UNSAFE_KEY_CHARACTERS.sub("-", PurePosixPath(path).name).strip(".-") or "file"
        uri = await storage_provider.store(
            resource.inline_bytes(),
            key=f"{storage_scope}/{BUNDLE_RESOURCES_STORAGE_PREFIX}/{resource.sha256}/{file_name}",
            content_type=mimetypes.guess_type(file_name)[0],
        )
        relocated[path] = resource.stored_at(uri=uri)
    return crate.model_copy(update={"bundle_resources": relocated})
