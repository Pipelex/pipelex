from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_factory import ConceptFactory
from pipelex.core.concepts.native.concept_native import NativeConceptCode
from pipelex.core.qualified_ref import QualifiedRef
from pipelex.libraries.concept.exceptions import ConceptLibraryError


def validate_concept_references_in_blueprints(
    blueprints: list[PipelexBundleBlueprint],
    already_loaded_concept_refs: set[str] | None = None,
) -> None:
    """Validate that every same-domain concept reference resolves against the merged library.

    Runs after the per-bundle structural merge, so a concept declared in one file can be
    referenced by bare code from a sibling file of the same domain — whether that sibling is in
    the same load batch or was loaded by a prior batch into the same library. References owned by
    another layer are deferred: cross-package refs ('alias->...') resolve at dependency-load time,
    and external-domain refs resolve when their own domain's bundles load. Native concepts are
    always available. Every unresolved reference is accumulated and reported together so the
    author sees all of them at once.

    Args:
        blueprints: The parsed bundles whose concept references are being checked. Their declared
            concepts form the batch's own declarations.
        already_loaded_concept_refs: Fully qualified concept refs already present in the live
            library from prior load batches (e.g. concepts loaded via a ``-L`` library directory).
            Adds the cross-batch context so a concept declared earlier still resolves. Native and
            cross-package entries in this set never satisfy a same-domain reference, so passing the
            whole library is harmless.

    Raises:
        ConceptLibraryError: If any same-domain/bare reference is neither declared (in this batch
            or already in the library) nor native.
    """
    # The batch's own declarations drive the error message, so the author sees exactly what these
    # files declare. The membership test additionally honors concepts loaded by prior batches.
    batch_declared_concept_refs: set[str] = {
        ConceptFactory.make_concept_ref_with_domain(domain_code=blueprint.domain, concept_code=concept_code)
        for blueprint in blueprints
        if blueprint.concept
        for concept_code in blueprint.concept
    }
    resolvable_concept_refs = batch_declared_concept_refs | (already_loaded_concept_refs or set())

    native_codes = {native.value for native in NativeConceptCode.values_list()}
    undeclared: list[str] = []
    for blueprint in blueprints:
        domain_code = blueprint.domain
        source = blueprint.source
        for concept_ref_or_code, context in blueprint.collect_concept_references():
            # Cross-package references are resolved at dependency-load time.
            if QualifiedRef.has_cross_package_prefix(concept_ref_or_code):
                continue
            ref = QualifiedRef.parse(concept_ref_or_code)
            # External-domain references resolve when their own domain's bundles load.
            if ref.is_external_to(domain_code):
                continue
            # Native concepts are always available. Use the canonical check (bare `Text` or
            # `native.Text` only) — not a bare local-code match — so a same-domain ref that merely
            # *shares* a native local code (e.g. `mydomain.Text`) is NOT mistaken for native and still
            # gets the membership check. This matches how the concept actually resolves
            # (ConceptLibrary.get_required_concept_from_concept_ref_or_code) and contract_match.
            if NativeConceptCode.is_native_concept_ref_or_code(concept_ref_or_code=concept_ref_or_code):
                continue
            concept_ref = ConceptFactory.make_concept_ref_with_domain(domain_code=domain_code, concept_code=ref.local_code)
            if concept_ref not in resolvable_concept_refs:
                undeclared.append(f"'{concept_ref_or_code}' in {context} is not declared in domain '{domain_code}' (source: '{source or 'unknown'}')")

    if undeclared:
        declared_list = sorted(batch_declared_concept_refs) if batch_declared_concept_refs else "(none)"
        msg = (
            "The following concept references could not be resolved against the merged library "
            "and are not native concepts:\n  - "
            + "\n  - ".join(undeclared)
            + f"\nDeclared concepts: {declared_list}."
            + f"\nNative concepts: {sorted(native_codes)}."
        )
        raise ConceptLibraryError(msg)
