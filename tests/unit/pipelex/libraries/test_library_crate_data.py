from typing import ClassVar

from pipelex.core.bundles.pipelex_bundle_blueprint import PipelexBundleBlueprint
from pipelex.core.concepts.concept_blueprint import ConceptBlueprint
from pipelex.pipe_operators.llm.pipe_llm_blueprint import PipeLLMBlueprint
from pipelex.pipe_signature.pipe_signature_blueprint import PipeSignatureBlueprint


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

    # For same-file collision tests: same source as SCORING_BUNDLE + same concept
    SCORING_SAME_FILE_DUPLICATE_CONCEPT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring.mthds",
        domain="scoring",
        description="Scoring domain same-file duplicate",
        concept={
            "WeightedScore": ConceptBlueprint(description="Same-file duplicate weighted score"),
        },
    )

    # For same-file collision tests: same source as SCORING_BUNDLE + same pipe
    SCORING_SAME_FILE_DUPLICATE_PIPE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/scoring.mthds",
        domain="scoring",
        description="Scoring domain same-file duplicate",
        pipe={
            "compute_score": PipeLLMBlueprint(
                description="Same-file duplicate compute score",
                output="Text",
                prompt="Same-file duplicate.",
            ),
        },
    )

    # For source=None edge case tests
    NONE_SOURCE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source=None,
        domain="nosource",
        description="Domain with no source file",
        concept={
            "Item": ConceptBlueprint(description="An item"),
        },
        pipe={
            "process_item": PipeLLMBlueprint(
                description="Process an item",
                output="Item",
                prompt="Process the item.",
            ),
        },
    )

    # For source=None collision tests: same domain + concept as NONE_SOURCE_BUNDLE
    NONE_SOURCE_DUPLICATE_CONCEPT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source=None,
        domain="nosource",
        description="Domain with no source file (duplicate)",
        concept={
            "Item": ConceptBlueprint(description="Duplicate item"),
        },
    )

    # --- Phase 1 (Part A): pipe signature/concrete reconciliation ---
    # All bundles below use the native concept Text in their contracts, so per-file
    # concept-reference validation passes without declaring any concept. The shared pipe
    # code is `summarize` with contract (inputs={"doc": "Text"}, output="Text").

    # Concrete definition of `summarize`.
    SIG_CONCRETE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document",
                inputs={"doc": "Text"},
                output="Text",
                prompt="Summarize $doc.",
            ),
        },
    )

    # Forward declaration (header) of `summarize` with a matching contract.
    SIG_SIGNATURE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize",
                inputs={"doc": "Text"},
                output="Text",
            ),
        },
    )

    # A second forward declaration of `summarize` with the same matching contract
    # (a sub-pipe forward-declared by several callers).
    SIG_SIGNATURE_DUP_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_2.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Second header for summarize",
                inputs={"doc": "Text"},
                output="Text",
            ),
        },
    )

    # A forward declaration of `summarize` with a mismatched contract (extra input).
    SIG_SIGNATURE_MISMATCH_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_bad.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Mismatched header for summarize",
                inputs={"doc": "Text", "lang": "Text"},
                output="Text",
            ),
        },
    )

    # A concrete definition of `summarize` whose contract mismatches the header (extra input).
    SIG_CONCRETE_MISMATCH_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_bad.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document in a language",
                inputs={"doc": "Text", "lang": "Text"},
                output="Text",
                prompt="Summarize $doc in $lang.",
            ),
        },
    )

    # A concrete definition of `summarize` with a matching contract but NO bundle source
    # (in-memory bundle). Exercises that a sourceless winner clears any stale source_map entry.
    SIG_CONCRETE_NO_SOURCE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source=None,
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document",
                inputs={"doc": "Text"},
                output="Text",
                prompt="Summarize $doc.",
            ),
        },
    )

    # A concrete definition of `summarize` that omits inputs entirely (mismatches the
    # explicit-inputs header under exact-match semantics).
    SIG_CONCRETE_NO_INPUTS_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_no_inputs.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize without declared inputs",
                output="Text",
                prompt="Summarize the document.",
            ),
        },
    )
