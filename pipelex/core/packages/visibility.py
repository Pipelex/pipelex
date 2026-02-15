from pydantic import BaseModel, ConfigDict

from pipelex import log
from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.packages.manifest import RESERVED_DOMAINS, MthdsPackageManifest, is_reserved_domain_path
from pipelex.core.qualified_ref import QualifiedRef, QualifiedRefError
from pipelex.pipe_controllers.condition.special_outcome import SpecialOutcome


class VisibilityError(BaseModel):
    """A single visibility violation."""

    model_config = ConfigDict(frozen=True)

    pipe_ref: str
    source_domain: str
    target_domain: str
    context: str
    message: str


class PackageVisibilityChecker:
    """Checks cross-domain pipe visibility against a manifest's exports.

    If no manifest is provided, all pipes are considered public (backward compat).
    """

    def __init__(
        self,
        manifest: MthdsPackageManifest | None,
        bundles: list[PipelexBundleBlueprint],
    ):
        self._manifest = manifest
        self._bundles = bundles

        # Build lookup: exported_pipes[domain_path] = set of pipe codes
        self._exported_pipes: dict[str, set[str]] = {}
        if manifest:
            for domain_export in manifest.exports:
                self._exported_pipes[domain_export.domain_path] = set(domain_export.pipes)

        # Build lookup: main_pipes[domain_path] = main_pipe code (auto-exported)
        self._main_pipes: dict[str, str] = {}
        for bundle in bundles:
            if bundle.main_pipe:
                existing = self._main_pipes.get(bundle.domain)
                if existing and existing != bundle.main_pipe:
                    log.warning(f"Conflicting main_pipe for domain '{bundle.domain}': '{existing}' vs '{bundle.main_pipe}' — keeping first value")
                else:
                    self._main_pipes[bundle.domain] = bundle.main_pipe

    def is_pipe_accessible_from(self, pipe_ref: QualifiedRef, source_domain: str) -> bool:
        """Check if a domain-qualified pipe ref is accessible from source_domain.

        Args:
            pipe_ref: The parsed pipe reference
            source_domain: The domain making the reference

        Returns:
            True if the pipe is accessible
        """
        # No manifest -> all pipes public
        if self._manifest is None:
            return True

        # Bare ref -> always allowed (no domain check)
        if not pipe_ref.is_qualified:
            return True

        # Same-domain ref -> always allowed
        if pipe_ref.is_local_to(source_domain):
            return True

        target_domain = pipe_ref.domain_path
        assert target_domain is not None
        pipe_code = pipe_ref.local_code

        # Check if it's in exports
        exported = self._exported_pipes.get(target_domain, set())
        if pipe_code in exported:
            return True

        # Check if it's a main_pipe (auto-exported)
        main_pipe = self._main_pipes.get(target_domain)
        return bool(main_pipe and pipe_code == main_pipe)

    def validate_all_pipe_references(self) -> list[VisibilityError]:
        """Validate all cross-domain pipe refs across all bundles.

        Returns:
            List of VisibilityError for each violation found
        """
        # No manifest -> no violations
        if self._manifest is None:
            return []

        errors: list[VisibilityError] = []
        special_outcomes = SpecialOutcome.value_list()

        for bundle in self._bundles:
            pipe_refs = bundle.collect_pipe_references()
            for pipe_ref_str, context in pipe_refs:
                # Skip special outcomes
                if pipe_ref_str in special_outcomes:
                    continue

                # Try to parse as pipe ref
                try:
                    ref = QualifiedRef.parse_pipe_ref(pipe_ref_str)
                except QualifiedRefError:
                    continue

                if not self.is_pipe_accessible_from(ref, bundle.domain):
                    target_domain = ref.domain_path or ""
                    msg = (
                        f"Pipe '{pipe_ref_str}' referenced in {context} (domain '{bundle.domain}') "
                        f"is not exported by domain '{target_domain}'. "
                        f"Add it to [exports.{target_domain}] pipes in METHODS.toml."
                    )
                    errors.append(
                        VisibilityError(
                            pipe_ref=pipe_ref_str,
                            source_domain=bundle.domain,
                            target_domain=target_domain,
                            context=context,
                            message=msg,
                        )
                    )

        return errors

    def validate_cross_package_references(self) -> list[VisibilityError]:
        """Validate cross-package references (using '->' syntax).

        Checks that:
        - If a ref contains '->' and the alias IS in dependencies -> emit warning (not error)
        - If a ref contains '->' and the alias is NOT in dependencies -> error

        Returns:
            List of VisibilityError for unknown dependency aliases
        """
        if self._manifest is None:
            return []

        # Build alias lookup from manifest dependencies
        known_aliases: set[str] = {dep.alias for dep in self._manifest.dependencies}

        errors: list[VisibilityError] = []

        for bundle in self._bundles:
            pipe_refs = bundle.collect_pipe_references()
            for pipe_ref_str, context in pipe_refs:
                if not QualifiedRef.has_cross_package_prefix(pipe_ref_str):
                    continue

                alias, _remainder = QualifiedRef.split_cross_package_ref(pipe_ref_str)

                if alias in known_aliases:
                    # Known alias -> informational (cross-package resolution is active)
                    log.info(
                        f"Cross-package reference '{pipe_ref_str}' in {context} (domain '{bundle.domain}'): alias '{alias}' is a known dependency."
                    )
                else:
                    # Unknown alias -> error
                    msg = (
                        f"Cross-package reference '{pipe_ref_str}' in {context} "
                        f"(domain '{bundle.domain}'): alias '{alias}' is not declared "
                        "in [dependencies] of METHODS.toml."
                    )
                    errors.append(
                        VisibilityError(
                            pipe_ref=pipe_ref_str,
                            source_domain=bundle.domain,
                            target_domain=alias,
                            context=context,
                            message=msg,
                        )
                    )

        return errors

    def validate_reserved_domains(self) -> list[VisibilityError]:
        """Check that no bundle declares a domain starting with a reserved segment.

        Returns:
            List of VisibilityError for each bundle using a reserved domain
        """
        errors: list[VisibilityError] = []

        for bundle in self._bundles:
            if is_reserved_domain_path(bundle.domain):
                first_segment = bundle.domain.split(".")[0]
                msg = (
                    f"Bundle domain '{bundle.domain}' uses reserved domain '{first_segment}'. "
                    f"Reserved domains ({', '.join(sorted(RESERVED_DOMAINS))}) cannot be used in user packages."
                )
                errors.append(
                    VisibilityError(
                        pipe_ref="",
                        source_domain=bundle.domain,
                        target_domain=first_segment,
                        context="bundle domain declaration",
                        message=msg,
                    )
                )

        return errors


def check_visibility_for_blueprints(
    manifest: MthdsPackageManifest | None,
    blueprints: list[PipelexBundleBlueprint],
) -> list[VisibilityError]:
    """Convenience function: check visibility for a set of blueprints.

    Validates both intra-package cross-domain visibility and cross-package references.

    Args:
        manifest: The package manifest (None means all-public)
        blueprints: The bundle blueprints to check

    Returns:
        List of visibility errors
    """
    checker = PackageVisibilityChecker(manifest=manifest, bundles=blueprints)
    errors = checker.validate_reserved_domains()
    errors.extend(checker.validate_all_pipe_references())
    errors.extend(checker.validate_cross_package_references())
    return errors
