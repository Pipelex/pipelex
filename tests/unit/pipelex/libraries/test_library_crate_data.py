from typing import ClassVar

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint


class BlueprintSamples:
    """Sample PipelexBundleBlueprint objects for testing LibraryCrate."""

    SCORING_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring.mthds",
        domain="scoring",
        description="Scoring domain",
        system_prompt="You are a scoring assistant.",
        concept={
            "WeightedScore": ConceptBlueprint(description="A weighted score"),
        },
        pipe={
            "compute_score": PipeLLMBlueprint(
                description="Compute a weighted score",
                output="WeightedScore",
                prompt="Compute the score.",
            ),
        },
    )

    SCORING_EXTRA_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring_extra.mthds",
        domain="scoring",
        description="Scoring domain (extra)",
        concept={
            "ScoreBreakdown": ConceptBlueprint(description="A breakdown of a score"),
        },
        pipe={
            "explain_score": PipeLLMBlueprint(
                description="Explain a score breakdown",
                output="ScoreBreakdown",
                prompt="Explain the score.",
            ),
        },
    )

    ANALYTICS_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/analytics.mthds",
        domain="analytics",
        description="Analytics domain",
        concept={
            "Metric": ConceptBlueprint(description="A metric"),
        },
        pipe={
            "compute_metric": PipeLLMBlueprint(
                description="Compute a metric",
                output="Metric",
                prompt="Compute the metric.",
            ),
        },
    )

    STRING_CONCEPT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/simple.mthds",
        domain="simple",
        description="Simple domain",
        concept={
            "MyConcept": "A simple concept described as a string",
        },
    )

    EMPTY_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/empty.mthds",
        domain="empty_domain",
        description="Empty domain",
    )

    # For collision tests: same domain + same concept code as SCORING_BUNDLE
    SCORING_DUPLICATE_CONCEPT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring_dup.mthds",
        domain="scoring",
        description="Scoring domain duplicate",
        concept={
            "WeightedScore": ConceptBlueprint(description="Duplicate weighted score"),
        },
    )

    # For collision tests: same domain + same pipe code as SCORING_BUNDLE
    SCORING_DUPLICATE_PIPE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring_dup.mthds",
        domain="scoring",
        description="Scoring domain duplicate",
        pipe={
            "compute_score": PipeLLMBlueprint(
                description="Duplicate compute score",
                output="Text",
                prompt="Duplicate.",
            ),
        },
    )
