"""The declaration tier of concept compatibility, exercised with no class registry at all.

`Concept.are_compatible_by_declaration` answers compatibility from the model's own fields — refs,
`structure_class_name` strings, `refines` chains, and the injected `concept_resolver` — and never
reaches for a class. That is what makes these rows expressible as plain constructor calls with
structure class names that no registry has ever heard of: if any row needed a class, it would fail
here rather than quietly resolve one from ambient process state.

`True` means "compatibility is established by the declarations"; `False` means "not established at
this tier" — never "incompatible". The class tier (`are_structure_classes_compatible`) and the
composition of the two (`ConceptLibrary.is_compatible`) are tested separately.
"""

from __future__ import annotations

import inspect

from pipelex.core.concepts.concept import Concept
from pipelex.core.concepts.native.concept_native import NativeConceptCode


def _make_concept(*, code: str, domain_code: str, structure_class_name: str, refines: str | None = None) -> Concept:
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name=structure_class_name,
        refines=refines,
    )


class TestConceptDeclarationCompatibility:
    def test_dynamic_concept_is_compatible_with_anything(self):
        """`Dynamic` short-circuits on either side — it is the untyped escape hatch."""
        dynamic = _make_concept(
            code=NativeConceptCode.DYNAMIC,
            domain_code="native",
            structure_class_name=NativeConceptCode.DYNAMIC.structure_class_name,
        )
        other = _make_concept(code="Whatever", domain_code="somewhere", structure_class_name="NeverRegisteredContent")

        assert Concept.are_compatible_by_declaration(concept_1=dynamic, concept_2=other) is True
        assert Concept.are_compatible_by_declaration(concept_1=other, concept_2=dynamic) is True

    def test_same_concept_ref_is_compatible(self):
        one = _make_concept(code="Invoice", domain_code="billing", structure_class_name="NeverRegisteredContent")
        same = _make_concept(code="Invoice", domain_code="billing", structure_class_name="AlsoNeverRegistered")

        assert Concept.are_compatible_by_declaration(concept_1=one, concept_2=same) is True

    def test_same_structure_class_name_is_compatible(self):
        one = _make_concept(code="Invoice", domain_code="billing", structure_class_name="NeverRegisteredContent")
        other = _make_concept(code="Receipt", domain_code="accounting", structure_class_name="NeverRegisteredContent")

        assert Concept.are_compatible_by_declaration(concept_1=one, concept_2=other) is True

    def test_refines_the_target_directly(self):
        base = _make_concept(code="BaseScore", domain_code="scoring", structure_class_name="BaseScoreContent")
        refining = _make_concept(
            code="DetailedScore",
            domain_code="scoring",
            structure_class_name="DetailedScoreContent",
            refines="scoring.BaseScore",
        )

        assert Concept.are_compatible_by_declaration(concept_1=refining, concept_2=base) is True

    def test_siblings_refining_the_same_concept(self):
        sibling_a = _make_concept(code="ScoreA", domain_code="my_domain", structure_class_name="ScoreAContent", refines="scoring.BaseScore")
        sibling_b = _make_concept(code="ScoreB", domain_code="my_domain", structure_class_name="ScoreBContent", refines="scoring.BaseScore")

        assert Concept.are_compatible_by_declaration(concept_1=sibling_a, concept_2=sibling_b) is True

    def test_unrelated_declarations_are_not_established(self):
        """Nothing in the declarations relates these two — the class tier would have to decide."""
        one = _make_concept(code="Invoice", domain_code="billing", structure_class_name="InvoiceContent")
        other = _make_concept(code="Portrait", domain_code="gallery", structure_class_name="PortraitContent")

        assert Concept.are_compatible_by_declaration(concept_1=one, concept_2=other) is False

    def test_cross_package_refines_resolves_through_the_resolver(self):
        target = _make_concept(code="WeightedScore", domain_code="scoring", structure_class_name="WeightedScoreContent")
        refining = _make_concept(
            code="RefinedScore",
            domain_code="my_domain",
            structure_class_name="RefinedScoreContent",
            refines="scoring_dep->scoring.WeightedScore",
        )

        def resolver(concept_ref: str) -> Concept | None:
            return target if concept_ref == "scoring_dep->scoring.WeightedScore" else None

        assert Concept.are_compatible_by_declaration(concept_1=refining, concept_2=target, concept_resolver=resolver) is True
        # Without the resolver the alias is an opaque string: not established at this tier.
        assert Concept.are_compatible_by_declaration(concept_1=refining, concept_2=target) is False

    def test_cross_package_siblings_resolve_through_the_resolver(self):
        base = _make_concept(code="BaseScore", domain_code="scoring", structure_class_name="BaseScoreContent")
        sibling_a = _make_concept(
            code="ScoreA",
            domain_code="my_domain",
            structure_class_name="ScoreAContent",
            refines="scoring_dep->scoring.BaseScore",
        )
        sibling_b = _make_concept(
            code="ScoreB",
            domain_code="other_domain",
            structure_class_name="ScoreBContent",
            refines="scoring_alias->scoring.BaseScore",
        )

        def resolver(concept_ref: str) -> Concept | None:
            return base if concept_ref in {"scoring_dep->scoring.BaseScore", "scoring_alias->scoring.BaseScore"} else None

        assert Concept.are_compatible_by_declaration(concept_1=sibling_a, concept_2=sibling_b, concept_resolver=resolver) is True

    def test_resolver_returning_none_leaves_it_unestablished(self):
        target = _make_concept(code="WeightedScore", domain_code="scoring", structure_class_name="WeightedScoreContent")
        refining = _make_concept(
            code="RefinedScore",
            domain_code="my_domain",
            structure_class_name="RefinedScoreContent",
            refines="unknown_dep->scoring.Missing",
        )

        def resolver(_concept_ref: str) -> Concept | None:
            return None

        assert Concept.are_compatible_by_declaration(concept_1=refining, concept_2=target, concept_resolver=resolver) is False

    def test_declaration_tier_takes_no_strict_flag(self):
        """Strictness governs the class tier only, so it is not a parameter here.

        Pinned as a signature fact: a caller that wants strict-mode semantics must go through
        `ConceptLibrary.is_compatible`, which owns the composition of the two tiers.
        """
        assert "strict" not in inspect.signature(Concept.are_compatible_by_declaration).parameters
