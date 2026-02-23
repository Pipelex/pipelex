"""Bridge between pipelex bundle blueprints and mthds package visibility.

Converts PipelexBundleBlueprint instances to BundleMetadata for use with
the mthds PackageVisibilityChecker.
"""

from mthds.packages.bundle_metadata import BundleMetadata
from mthds.packages.manifest import MthdsPackageManifest
from mthds.packages.visibility import PackageVisibilityChecker, VisibilityError

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint


def _blueprint_to_metadata(blueprint: PipelexBundleBlueprint) -> BundleMetadata:
    """Convert a PipelexBundleBlueprint to BundleMetadata.

    Extracts domain, main_pipe, and pipe references from the
    blueprint for use with the mthds visibility checker.

    Args:
        blueprint: The pipelex bundle blueprint.

    Returns:
        A BundleMetadata instance.
    """
    pipe_references: list[tuple[str, str]] = blueprint.collect_pipe_references()

    return BundleMetadata(
        domain=blueprint.domain,
        main_pipe=blueprint.main_pipe,
        pipe_references=pipe_references,
    )


def make_visibility_checker(
    manifest: MthdsPackageManifest | None,
    blueprints: list[PipelexBundleBlueprint],
) -> PackageVisibilityChecker:
    """Create a PackageVisibilityChecker from pipelex blueprints.

    Args:
        manifest: The package manifest (None means all-public).
        blueprints: The pipelex bundle blueprints to check.

    Returns:
        A configured PackageVisibilityChecker.
    """
    metadatas = [_blueprint_to_metadata(blueprint) for blueprint in blueprints]
    return PackageVisibilityChecker(manifest=manifest, bundle_metadatas=metadatas)


def check_visibility_for_blueprints(
    manifest: MthdsPackageManifest | None,
    blueprints: list[PipelexBundleBlueprint],
) -> list[VisibilityError]:
    """Convenience function: check visibility for pipelex blueprints.

    Validates both intra-package cross-domain visibility and cross-package references.

    Args:
        manifest: The package manifest (None means all-public).
        blueprints: The pipelex bundle blueprints to check.

    Returns:
        List of visibility errors.
    """
    checker = make_visibility_checker(manifest=manifest, blueprints=blueprints)
    errors = checker.validate_reserved_domains()
    errors.extend(checker.validate_all_pipe_references())
    errors.extend(checker.validate_cross_package_references())
    return errors
