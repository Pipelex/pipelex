# Deferred items — Phase 1 code review (Checkpoint 1)

Context-free review of commit `757146324` (Phase 1: always-combine PipeParallel). No correctness bugs found. Triage outcome of the two cleanup findings:

## Fixed at checkpoint

- **Duplicated native-concept rejection match** between `PipeParallel.validate_output_static` and `PipeParallelBlueprint.validate_output` — extracted into `NativeConceptCode.is_composite` (exhaustive match lives once, on the enum, per house style). Both validators now branch on the property.

## Deferred (design tradeoff, not a bug)

- **Double-parse of the pipe output string in blueprint validation.** `PipeBlueprint.generic_validate_output` parses `self.output` with `parse_concept_with_multiplicity`, then `PipeParallelBlueprint.validate_output` parses the same string again. Avoiding it means changing the `validate_output()` hook signature across every blueprint subclass to thread the `MultiplicityParseResult` through. This runs once per pipe definition at load time — not a hot path — so the signature churn across all pipe blueprints isn't worth it today. Revisit only if a blueprint-validation hook redesign happens for other reasons.
