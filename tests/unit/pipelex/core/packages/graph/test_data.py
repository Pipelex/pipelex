"""Shared test data for know-how graph tests.

Builds a test PackageIndex with 4 packages:

| Package       | Address                              | Concepts                  | Pipes (exported)                                              |
|---------------|--------------------------------------|---------------------------|---------------------------------------------------------------|
| scoring-lib   | github.com/pkg_test/scoring-lib      | PkgTestWeightedScore      | pkg_test_compute_score (Text -> PkgTestWeightedScore)         |
| refining-app  | github.com/pkg_test/refining-app     | PkgTestRefinedScore       | pkg_test_refine_score (Text -> PkgTestRefinedScore)           |
|               |                                      | (refines scoring's WS)    |                                                               |
| legal-tools   | github.com/pkg_test/legal-tools      | PkgTestContractClause     | pkg_test_extract_clause (Text -> PkgTestContractClause)       |
|               |                                      |                           | pkg_test_analyze_clause (PkgTestContractClause -> Text)       |
| analytics-lib | github.com/pkg_test/analytics-lib    | PkgTestWeightedScore      | pkg_test_compute_analytics (Text -> PkgTestWeightedScore)     |
|               |                                      | (same code, different pkg)|                                                               |
"""

from pipelex.core.packages.index.models import (
    ConceptEntry,
    DomainEntry,
    PackageIndex,
    PackageIndexEntry,
    PipeSignature,
)

SCORING_LIB_ADDRESS = "github.com/pkg_test/scoring-lib"
REFINING_APP_ADDRESS = "github.com/pkg_test/refining-app"
LEGAL_TOOLS_ADDRESS = "github.com/pkg_test/legal-tools"
ANALYTICS_LIB_ADDRESS = "github.com/pkg_test/analytics-lib"
PHANTOM_PKG_ADDRESS = "github.com/pkg_test/phantom-pkg"
QUALIFIED_REF_ADDRESS = "github.com/pkg_test/qualified-ref-pkg"
MALFORMED_REF_ADDRESS = "github.com/pkg_test/malformed-ref-pkg"
MULTI_DOMAIN_PKG_ADDRESS = "github.com/pkg_test/multi-domain-pkg"
MULTI_DOMAIN_CONSUMER_ADDRESS = "github.com/pkg_test/multi-domain-consumer"


def make_test_package_index() -> PackageIndex:
    """Build a PackageIndex with 4 test packages for graph tests."""
    index = PackageIndex()

    # --- scoring-lib ---
    scoring_lib = PackageIndexEntry(
        address=SCORING_LIB_ADDRESS,
        version="1.0.0",
        description="Scoring library",
        domains=[DomainEntry(domain_code="pkg_test_scoring_dep")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestWeightedScore",
                domain_code="pkg_test_scoring_dep",
                concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
                description="A weighted score",
                structure_fields=["score_value", "weight"],
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_compute_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_scoring_dep",
                description="Compute weighted score from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestWeightedScore",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(scoring_lib)

    # --- refining-app (depends on scoring-lib, refines its concept) ---
    refining_app = PackageIndexEntry(
        address=REFINING_APP_ADDRESS,
        version="1.0.0",
        description="Refining application",
        domains=[DomainEntry(domain_code="pkg_test_refining")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestRefinedScore",
                domain_code="pkg_test_refining",
                concept_ref="pkg_test_refining.PkgTestRefinedScore",
                description="A refined score",
                refines="scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_refine_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_refining",
                description="Refine a score from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestRefinedScore",
                is_exported=True,
            ),
        ],
        dependencies=[SCORING_LIB_ADDRESS],
        dependency_aliases={"scoring_dep": SCORING_LIB_ADDRESS},
    )
    index.add_entry(refining_app)

    # --- legal-tools ---
    legal_tools = PackageIndexEntry(
        address=LEGAL_TOOLS_ADDRESS,
        version="1.0.0",
        description="Legal document analysis tools",
        domains=[DomainEntry(domain_code="pkg_test_legal")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestContractClause",
                domain_code="pkg_test_legal",
                concept_ref="pkg_test_legal.PkgTestContractClause",
                description="A clause from a contract",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_extract_clause",
                pipe_type="PipeLLM",
                domain_code="pkg_test_legal",
                description="Extract clause from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestContractClause",
                is_exported=True,
            ),
            PipeSignature(
                pipe_code="pkg_test_analyze_clause",
                pipe_type="PipeLLM",
                domain_code="pkg_test_legal",
                description="Analyze a contract clause",
                input_specs={"clause": "PkgTestContractClause"},
                output_spec="Text",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(legal_tools)

    # --- analytics-lib (same concept code PkgTestWeightedScore but different package) ---
    analytics_lib = PackageIndexEntry(
        address=ANALYTICS_LIB_ADDRESS,
        version="1.0.0",
        description="Analytics library",
        domains=[DomainEntry(domain_code="pkg_test_analytics")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestWeightedScore",
                domain_code="pkg_test_analytics",
                concept_ref="pkg_test_analytics.PkgTestWeightedScore",
                description="An analytics weighted score",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_compute_analytics",
                pipe_type="PipeLLM",
                domain_code="pkg_test_analytics",
                description="Compute analytics score from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestWeightedScore",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(analytics_lib)

    return index


def make_test_package_index_with_unresolvable_concepts() -> PackageIndex:
    """Build a PackageIndex containing pipes with unresolvable concept references.

    Creates a package with:
    - One valid concept (PkgTestValidConcept)
    - One pipe with a valid output concept (pkg_test_valid_pipe)
    - One pipe whose output references a nonexistent concept (pkg_test_bad_output_pipe)
    - One pipe whose input references a nonexistent concept (pkg_test_bad_input_pipe)
    """
    index = PackageIndex()

    phantom_pkg = PackageIndexEntry(
        address=PHANTOM_PKG_ADDRESS,
        version="1.0.0",
        description="Package with unresolvable concept references",
        domains=[DomainEntry(domain_code="pkg_test_phantom")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestValidConcept",
                domain_code="pkg_test_phantom",
                concept_ref="pkg_test_phantom.PkgTestValidConcept",
                description="A valid concept",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_valid_pipe",
                pipe_type="PipeLLM",
                domain_code="pkg_test_phantom",
                description="Valid pipe with resolvable concepts",
                input_specs={"text": "Text"},
                output_spec="PkgTestValidConcept",
                is_exported=True,
            ),
            PipeSignature(
                pipe_code="pkg_test_bad_output_pipe",
                pipe_type="PipeLLM",
                domain_code="pkg_test_phantom",
                description="Pipe with unresolvable output concept",
                input_specs={"text": "Text"},
                output_spec="NonExistentOutputConcept",
                is_exported=True,
            ),
            PipeSignature(
                pipe_code="pkg_test_bad_input_pipe",
                pipe_type="PipeLLM",
                domain_code="pkg_test_phantom",
                description="Pipe with unresolvable input concept",
                input_specs={"data": "NonExistentInputConcept"},
                output_spec="PkgTestValidConcept",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(phantom_pkg)

    return index


def make_test_package_index_with_qualified_concept_specs() -> PackageIndex:
    """Build a PackageIndex with pipes that use domain-qualified and cross-package concept specs.

    Creates:
    - scoring-lib with PkgTestWeightedScore in domain pkg_test_scoring_dep
    - qualified-ref-pkg that:
      - Has its own concept PkgTestLocalResult in domain pkg_test_qualified
      - Depends on scoring-lib (alias: scoring_dep)
      - Has a pipe using a domain-qualified output spec (pkg_test_qualified.PkgTestLocalResult)
      - Has a pipe using a cross-package input spec (scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore)
    """
    index = PackageIndex()

    # scoring-lib (dependency)
    scoring_lib = PackageIndexEntry(
        address=SCORING_LIB_ADDRESS,
        version="1.0.0",
        description="Scoring library",
        domains=[DomainEntry(domain_code="pkg_test_scoring_dep")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestWeightedScore",
                domain_code="pkg_test_scoring_dep",
                concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
                description="A weighted score",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_compute_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_scoring_dep",
                description="Compute score from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestWeightedScore",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(scoring_lib)

    # qualified-ref-pkg (consumer with qualified concept specs)
    qualified_ref_pkg = PackageIndexEntry(
        address=QUALIFIED_REF_ADDRESS,
        version="1.0.0",
        description="Package using qualified concept references in pipes",
        domains=[DomainEntry(domain_code="pkg_test_qualified")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestLocalResult",
                domain_code="pkg_test_qualified",
                concept_ref="pkg_test_qualified.PkgTestLocalResult",
                description="A local result concept",
            ),
        ],
        pipes=[
            # Pipe with domain-qualified output spec
            PipeSignature(
                pipe_code="pkg_test_produce_result",
                pipe_type="PipeLLM",
                domain_code="pkg_test_qualified",
                description="Produce a local result from text",
                input_specs={"text": "Text"},
                output_spec="pkg_test_qualified.PkgTestLocalResult",
                is_exported=True,
            ),
            # Pipe with cross-package input spec
            PipeSignature(
                pipe_code="pkg_test_consume_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_qualified",
                description="Consume a cross-package weighted score",
                input_specs={"score": "scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore"},
                output_spec="Text",
                is_exported=True,
            ),
            # Pipe with cross-package output spec
            PipeSignature(
                pipe_code="pkg_test_forward_score",
                pipe_type="PipeLLM",
                domain_code="pkg_test_qualified",
                description="Forward a cross-package score",
                input_specs={"text": "Text"},
                output_spec="scoring_dep->pkg_test_scoring_dep.PkgTestWeightedScore",
                is_exported=True,
            ),
        ],
        dependencies=[SCORING_LIB_ADDRESS],
        dependency_aliases={"scoring_dep": SCORING_LIB_ADDRESS},
    )
    index.add_entry(qualified_ref_pkg)

    return index


def make_test_package_index_with_malformed_cross_package_ref() -> PackageIndex:
    """Build a PackageIndex with a pipe whose cross-package remainder is malformed.

    Creates a package with:
    - One valid concept (PkgTestValidConcept)
    - One valid pipe (pkg_test_valid_pipe) that uses bare concept codes
    - One pipe (pkg_test_malformed_ref_pipe) whose output spec is a cross-package ref
      with a malformed remainder (e.g. "scoring_dep->..BadRef") that would cause
      QualifiedRefError if not caught
    - scoring-lib as a dependency so the alias resolves
    """
    index = PackageIndex()

    # scoring-lib (dependency)
    scoring_lib = PackageIndexEntry(
        address=SCORING_LIB_ADDRESS,
        version="1.0.0",
        description="Scoring library",
        domains=[DomainEntry(domain_code="pkg_test_scoring_dep")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestWeightedScore",
                domain_code="pkg_test_scoring_dep",
                concept_ref="pkg_test_scoring_dep.PkgTestWeightedScore",
                description="A weighted score",
            ),
        ],
        pipes=[],
    )
    index.add_entry(scoring_lib)

    malformed_pkg = PackageIndexEntry(
        address=MALFORMED_REF_ADDRESS,
        version="1.0.0",
        description="Package with malformed cross-package refs",
        domains=[DomainEntry(domain_code="pkg_test_malformed")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestValidConcept",
                domain_code="pkg_test_malformed",
                concept_ref="pkg_test_malformed.PkgTestValidConcept",
                description="A valid concept",
            ),
        ],
        pipes=[
            # Valid pipe — should survive even if sibling has malformed ref
            PipeSignature(
                pipe_code="pkg_test_valid_pipe",
                pipe_type="PipeLLM",
                domain_code="pkg_test_malformed",
                description="Valid pipe with resolvable concepts",
                input_specs={"text": "Text"},
                output_spec="PkgTestValidConcept",
                is_exported=True,
            ),
            # Malformed cross-package ref: remainder starts with ".."
            PipeSignature(
                pipe_code="pkg_test_malformed_ref_pipe",
                pipe_type="PipeLLM",
                domain_code="pkg_test_malformed",
                description="Pipe with malformed cross-package remainder",
                input_specs={"text": "Text"},
                output_spec="scoring_dep->..BadRef",
                is_exported=True,
            ),
        ],
        dependencies=[SCORING_LIB_ADDRESS],
        dependency_aliases={"scoring_dep": SCORING_LIB_ADDRESS},
    )
    index.add_entry(malformed_pkg)

    return index


def make_test_package_index_with_multi_domain_same_concept_code() -> PackageIndex:
    """Build a PackageIndex where one package has the same concept code in two domains.

    This tests that cross-package resolution picks the correct domain when
    ``alias->domain.ConceptCode`` is used and the target package has that
    concept code in multiple domains.

    Creates:
    - multi-domain-pkg with:
      - Domain pkg_test_scoring: PkgTestMetric (concept_ref: pkg_test_scoring.PkgTestMetric)
      - Domain pkg_test_analytics: PkgTestMetric (concept_ref: pkg_test_analytics.PkgTestMetric)
      - Two pipes producing each variant
    - multi-domain-consumer that:
      - Depends on multi-domain-pkg (alias: multi_domain)
      - Has a pipe consuming multi_domain->pkg_test_scoring.PkgTestMetric
      - Has a pipe consuming multi_domain->pkg_test_analytics.PkgTestMetric
    """
    index = PackageIndex()

    multi_domain_pkg = PackageIndexEntry(
        address=MULTI_DOMAIN_PKG_ADDRESS,
        version="1.0.0",
        description="Package with same concept code in two domains",
        domains=[
            DomainEntry(domain_code="pkg_test_scoring"),
            DomainEntry(domain_code="pkg_test_analytics"),
        ],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestMetric",
                domain_code="pkg_test_scoring",
                concept_ref="pkg_test_scoring.PkgTestMetric",
                description="A scoring metric",
                structure_fields=["score_value"],
            ),
            ConceptEntry(
                concept_code="PkgTestMetric",
                domain_code="pkg_test_analytics",
                concept_ref="pkg_test_analytics.PkgTestMetric",
                description="An analytics metric",
                structure_fields=["analytics_value"],
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_compute_scoring_metric",
                pipe_type="PipeLLM",
                domain_code="pkg_test_scoring",
                description="Compute scoring metric from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestMetric",
                is_exported=True,
            ),
            PipeSignature(
                pipe_code="pkg_test_compute_analytics_metric",
                pipe_type="PipeLLM",
                domain_code="pkg_test_analytics",
                description="Compute analytics metric from text",
                input_specs={"text": "Text"},
                output_spec="PkgTestMetric",
                is_exported=True,
            ),
        ],
    )
    index.add_entry(multi_domain_pkg)

    multi_domain_consumer = PackageIndexEntry(
        address=MULTI_DOMAIN_CONSUMER_ADDRESS,
        version="1.0.0",
        description="Consumer that references specific domains of multi-domain-pkg",
        domains=[DomainEntry(domain_code="pkg_test_consumer")],
        concepts=[
            ConceptEntry(
                concept_code="PkgTestConsumerResult",
                domain_code="pkg_test_consumer",
                concept_ref="pkg_test_consumer.PkgTestConsumerResult",
                description="A consumer result",
            ),
        ],
        pipes=[
            PipeSignature(
                pipe_code="pkg_test_use_scoring_metric",
                pipe_type="PipeLLM",
                domain_code="pkg_test_consumer",
                description="Use scoring metric from dependency",
                input_specs={"metric": "multi_domain->pkg_test_scoring.PkgTestMetric"},
                output_spec="Text",
                is_exported=True,
            ),
            PipeSignature(
                pipe_code="pkg_test_use_analytics_metric",
                pipe_type="PipeLLM",
                domain_code="pkg_test_consumer",
                description="Use analytics metric from dependency",
                input_specs={"metric": "multi_domain->pkg_test_analytics.PkgTestMetric"},
                output_spec="Text",
                is_exported=True,
            ),
        ],
        dependencies=[MULTI_DOMAIN_PKG_ADDRESS],
        dependency_aliases={"multi_domain": MULTI_DOMAIN_PKG_ADDRESS},
    )
    index.add_entry(multi_domain_consumer)

    return index
