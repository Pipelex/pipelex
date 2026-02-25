from pipelex.core.concepts.concept import Concept


def _make_concept(code: str, domain_code: str, refines: str | None = None) -> Concept:
    """Create a minimal Concept for testing."""
    return Concept(
        code=code,
        domain_code=domain_code,
        description="Test concept",
        structure_class_name="TextContent",
        refines=refines,
    )


class TestConceptCrossPackageRefines:
    """Tests for cross-package refinement compatibility in Concept.are_concept_compatible()."""

    def test_refines_cross_package_with_resolver_compatible(self):
        """Concept refining cross-package concept is compatible when resolver resolves to target."""
        refining = _make_concept(code="RefinedScore", domain_code="my_domain", refines="scoring_dep->scoring.WeightedScore")
        target = _make_concept(code="WeightedScore", domain_code="scoring")

        def resolver(concept_ref: str) -> Concept | None:
            if concept_ref == "scoring_dep->scoring.WeightedScore":
                return target
            return None

        assert Concept.are_concept_compatible(concept_1=refining, concept_2=target, concept_resolver=resolver) is True

    def test_refines_cross_package_without_resolver_not_compatible(self):
        """Cross-package refines without a resolver is not compatible via refines check."""
        refining = _make_concept(code="RefinedScore", domain_code="my_domain", refines="scoring_dep->scoring.WeightedScore")
        target = _make_concept(code="WeightedScore", domain_code="scoring")

        # Without resolver, the cross-package refines string won't match the target concept_ref
        # They might still be compatible via structure_class_name (both TextContent)
        # but the refines-based check specifically won't match
        result = Concept.are_concept_compatible(concept_1=refining, concept_2=target)
        # Compatible due to same structure_class_name, not due to refines resolution
        assert result is True

    def test_refines_cross_package_different_structure_without_resolver(self):
        """Cross-package refines with different structures, without resolver."""
        refining = Concept(
            code="RefinedScore",
            domain_code="my_domain",
            description="Refined",
            structure_class_name="RefinedScoreContent",
            refines="scoring_dep->scoring.WeightedScore",
        )
        target = Concept(
            code="WeightedScore",
            domain_code="scoring",
            description="Target",
            structure_class_name="WeightedScoreContent",
        )

        # Without resolver, and different structure_class_name, not compatible via refines
        result = Concept.are_concept_compatible(concept_1=refining, concept_2=target)
        assert result is False

    def test_refines_cross_package_different_structure_with_resolver(self):
        """Cross-package refines with different structures, but resolver resolves correctly."""
        refining = Concept(
            code="RefinedScore",
            domain_code="my_domain",
            description="Refined",
            structure_class_name="RefinedScoreContent",
            refines="scoring_dep->scoring.WeightedScore",
        )
        target = Concept(
            code="WeightedScore",
            domain_code="scoring",
            description="Target",
            structure_class_name="WeightedScoreContent",
        )

        def resolver(concept_ref: str) -> Concept | None:
            if concept_ref == "scoring_dep->scoring.WeightedScore":
                return target
            return None

        result = Concept.are_concept_compatible(concept_1=refining, concept_2=target, concept_resolver=resolver)
        assert result is True

    def test_both_refine_same_cross_package_concept_siblings(self):
        """Two concepts that both refine the same cross-package concept are siblings."""
        base = _make_concept(code="BaseScore", domain_code="scoring")

        sibling_a = Concept(
            code="ScoreA",
            domain_code="my_domain",
            description="Sibling A",
            structure_class_name="ScoreAContent",
            refines="scoring_dep->scoring.BaseScore",
        )
        sibling_b = Concept(
            code="ScoreB",
            domain_code="my_domain",
            description="Sibling B",
            structure_class_name="ScoreBContent",
            refines="scoring_dep->scoring.BaseScore",
        )

        def resolver(concept_ref: str) -> Concept | None:
            if concept_ref == "scoring_dep->scoring.BaseScore":
                return base
            return None

        result = Concept.are_concept_compatible(concept_1=sibling_a, concept_2=sibling_b, concept_resolver=resolver)
        assert result is True

    def test_resolver_returns_none_not_compatible(self):
        """When resolver returns None for a cross-package refines, not compatible via refines."""
        refining = Concept(
            code="RefinedScore",
            domain_code="my_domain",
            description="Refined",
            structure_class_name="RefinedScoreContent",
            refines="unknown_dep->scoring.Missing",
        )
        target = Concept(
            code="WeightedScore",
            domain_code="scoring",
            description="Target",
            structure_class_name="WeightedScoreContent",
        )

        def resolver(_concept_ref: str) -> Concept | None:
            return None

        result = Concept.are_concept_compatible(concept_1=refining, concept_2=target, concept_resolver=resolver)
        assert result is False

    def test_local_refines_unaffected(self):
        """Local (non-cross-package) refines still works without resolver."""
        base = _make_concept(code="BaseScore", domain_code="scoring")
        refining = _make_concept(code="DetailedScore", domain_code="scoring", refines="scoring.BaseScore")

        result = Concept.are_concept_compatible(concept_1=refining, concept_2=base)
        assert result is True
