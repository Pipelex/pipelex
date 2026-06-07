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

    # --- Phase 2 (Part B): cross-file concept references resolve at library level ---
    # `crossref` declares a non-native concept `Summary` in one file and references it by bare
    # code from a sibling file of the same domain. With per-file validation gone, both files
    # construct, and the reference resolves against the merged crate.

    # File A: declares the non-native concept `Summary`.
    CROSSREF_CONCEPT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/crossref_concept.mthds",
        domain="crossref",
        description="Cross-reference domain",
        concept={
            "Summary": ConceptBlueprint(description="A summary of a document"),
        },
    )

    # File B: a pipe that references `Summary` (declared in file A) by bare code.
    CROSSREF_PIPE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/crossref_pipe.mthds",
        domain="crossref",
        description="Cross-reference domain",
        pipe={
            "make_summary": PipeLLMBlueprint(
                description="Summarize a document",
                inputs={"doc": "Text"},
                output="Summary",
                prompt="Summarize $doc.",
            ),
        },
    )

    # --- Normalized contract conformance: bare <-> qualified <-> native equivalence ---
    # The merge is a pure structural step (no concept-ref validation), so these contracts may name
    # an undeclared concept `Summary`; only the contract identity matters here. All share the pipe
    # code `summarize` in domain `reconcile` so they collide with each other / SIG_CONCRETE_BUNDLE.

    # Header whose output is the same-domain concept written bare: `Summary`.
    SIG_SIGNATURE_BARE_SUMMARY_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_bare_summary.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (bare Summary output)",
                inputs={"doc": "Text"},
                output="Summary",
            ),
        },
    )

    # Concrete whose output is the SAME concept written domain-qualified: `reconcile.Summary`.
    # Normalized identity makes this reconcile with SIG_SIGNATURE_BARE_SUMMARY_BUNDLE.
    SIG_CONCRETE_QUALIFIED_SUMMARY_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_qualified_summary.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document",
                inputs={"doc": "Text"},
                output="reconcile.Summary",
                prompt="Summarize $doc.",
            ),
        },
    )

    # Header whose contract uses the native concept in its fully-qualified form (`native.Text`).
    # Normalized identity makes this reconcile with SIG_CONCRETE_BUNDLE (bare `Text`).
    SIG_SIGNATURE_NATIVE_QUALIFIED_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_native_qualified.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (native.Text contract)",
                inputs={"doc": "native.Text"},
                output="native.Text",
            ),
        },
    )

    # Header with a list-valued output written bare: `Summary[]`.
    SIG_SIGNATURE_LIST_BARE_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_list_bare.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (Summary[] output)",
                inputs={"doc": "Text"},
                output="Summary[]",
            ),
        },
    )

    # Concrete with the SAME list-valued output written domain-qualified: `reconcile.Summary[]`.
    SIG_CONCRETE_LIST_QUALIFIED_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_list_qualified.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document into key points",
                inputs={"doc": "Text"},
                output="reconcile.Summary[]",
                prompt="Summarize $doc.",
            ),
        },
    )

    # Header whose output is a genuinely DIFFERENT same-domain concept: `Brief` (not `Summary`).
    SIG_SIGNATURE_BRIEF_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_brief.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (Brief output)",
                inputs={"doc": "Text"},
                output="Brief",
            ),
        },
    )

    # Header with a FIXED-count list output `Summary[2]` — distinct from the variable-length
    # `Summary[]` (pins that `[]` and `[N]` must not be conflated via Python's `True == 1`).
    SIG_SIGNATURE_LIST_FIXED_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_list_fixed.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (Summary[2] output)",
                inputs={"doc": "Text"},
                output="Summary[2]",
            ),
        },
    )

    # Concrete with the SAME fixed-count output, domain-qualified: `reconcile.Summary[2]`.
    SIG_CONCRETE_LIST_FIXED_QUALIFIED_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_list_fixed_qualified.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document into exactly two points",
                inputs={"doc": "Text"},
                output="reconcile.Summary[2]",
                prompt="Summarize $doc.",
            ),
        },
    )

    # Concrete with a list output of EXACTLY ONE, domain-qualified: `reconcile.Summary[1]`. Paired
    # against `Summary[]` this is the precise regression guard: parsing `[]`->True and `[1]`->int 1
    # and comparing them conflates the two because Python evaluates `True == 1` as true.
    SIG_CONCRETE_LIST_ONE_QUALIFIED_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_list_one_qualified.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document into exactly one point",
                inputs={"doc": "Text"},
                output="reconcile.Summary[1]",
                prompt="Summarize $doc.",
            ),
        },
    )

    # Header whose output is an EXTERNAL-domain concept `other_domain.Insight` — must NOT canonicalize
    # to `reconcile.Insight`, so it stays distinct from a same-domain `Insight`.
    SIG_SIGNATURE_EXTERNAL_OUTPUT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_header_external.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeSignatureBlueprint(
                description="Header for summarize (external-domain output)",
                inputs={"doc": "Text"},
                output="other_domain.Insight",
            ),
        },
    )

    # Concrete with the SAME external-domain output `other_domain.Insight` — kept verbatim, matches.
    SIG_CONCRETE_EXTERNAL_OUTPUT_BUNDLE: ClassVar[PipelexBundleBlueprint] = PipelexBundleBlueprint(
        source="/fake/reconcile_concrete_external.mthds",
        domain="reconcile",
        description="Reconciliation domain",
        pipe={
            "summarize": PipeLLMBlueprint(
                description="Summarize a document into an insight",
                inputs={"doc": "Text"},
                output="other_domain.Insight",
                prompt="Summarize $doc.",
            ),
        },
    )
