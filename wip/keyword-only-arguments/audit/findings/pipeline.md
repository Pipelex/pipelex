# Suspects — package `pipeline`

Reviewed: 18 Section A + 4 primitive lone-subjects. Suspects: 1.

## High confidence

None.

## Medium / low confidence

- `pipelex/pipeline/job_metadata.py:89` — `JobMetadata.copy_with_update` — `def copy_with_update(self, otel_context: OtelContext | None, *, trace_context: TraceContext | None = None, **updates: Any)` — `otel_context` is not the subject being acted on (that's `self`, the metadata object); it's one of two context fields being updated, asymmetrically split from `trace_context` across the `*` boundary. Call sites always pass it as a keyword (`otel_context=...`) and the docstring justifies the asymmetry semantically (different inheritance semantics), but from a signature-readability standpoint both context args are peers. Suggested fix: make fully keyword-only — `def copy_with_update(self, *, otel_context: OtelContext | None, trace_context: TraceContext | None = None, **updates: Any)`.
