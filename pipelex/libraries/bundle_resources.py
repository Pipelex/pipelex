"""The files submitted with bundles loaded from content strings, checked against the steps that name them.

`pipelex.core.bundle_resources.bundle_resource` says how a submitted file is keyed. This module holds the library
layer's one check on them: every submitted file must be one a step names, so a misspelt key fails loudly rather than
leaving the step without its file.
"""

from collections.abc import Iterable, Mapping

from pipelex.core.bundle_resources.bundle_resource import canonical_resource_path_or_none, canonical_submitted_files
from pipelex.core.bundle_resources.exceptions import BundleResourceNotNamedError
from pipelex.mthds_parsing.pipelex_bundle_blueprint import PipeBlueprintUnion, PipelexBundleBlueprint


def named_bundle_files(*, pipe_blueprints: Iterable[PipeBlueprintUnion]) -> set[str]:
    """The bundle files these pipes name, by canonical path.

    A path no file submitted with a bundle can have, such as one with a `..` segment, is left out: no submitted file
    can answer it, and the step that names it is refused when its blueprint validates.
    """
    named: set[str] = set()
    for pipe_blueprint in pipe_blueprints:
        for named_path in pipe_blueprint.named_file_references:
            canonical_path = canonical_resource_path_or_none(path=named_path)
            if canonical_path is not None:
                named.add(canonical_path)
    return named


def check_submitted_files(*, blueprints: Iterable[PipelexBundleBlueprint], submitted_files: Mapping[str, bytes]) -> None:
    """Refuse a file submitted with the bundles that none of their steps names, whatever spelling of its path it is keyed by.

    Raises:
        BundleResourcePathError: a submitted file's path cannot name a file inside the bundle, or two name the same file.
        BundleResourceNotNamedError: a submitted file is named by no step of the bundles.
    """
    if not submitted_files:
        return
    pipe_blueprints = [pipe_blueprint for blueprint in blueprints for pipe_blueprint in (blueprint.pipe or {}).values()]
    submitted_paths = set(canonical_submitted_files(files=submitted_files))
    unnamed_paths = sorted(submitted_paths - named_bundle_files(pipe_blueprints=pipe_blueprints))
    if unnamed_paths:
        listed = ", ".join(f"'{path}'" for path in unnamed_paths)
        msg = (
            f"The bundle was submitted with files none of its steps names: {listed}. Submit only the files a step reads, "
            "each keyed by the path the step names, such as a PipeDocGen step's 'template_file', relative to the bundle."
        )
        raise BundleResourceNotNamedError(msg).with_params(field="resources")
