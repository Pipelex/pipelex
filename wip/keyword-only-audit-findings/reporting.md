# Suspects — package `reporting`

Reviewed: 5 Section A + 1 primitive lone-subject. Suspects: 1.

## Medium / low confidence

- `pipelex/reporting/reporting_manager.py:251` — `ReportingManager._emit_best_effort` — `def _emit_best_effort(event_log: EventLogProtocol, *, event: UsageReportEvent) -> None` — `event` is the semantic object being emitted; `event_log` is the target/sink the function dispatches to via `event_log.emit(event)`. Both call sites already pass `event_log` as a keyword (`_emit_best_effort(event_log=..., event=...)`), suggesting callers don't treat it as an obvious positional subject. The function name "emit best effort" designates the action, not the receiver, so neither arg has a clear claim as the one true subject — suggested fix: make fully keyword-only (`def _emit_best_effort(*, event_log: EventLogProtocol, event: UsageReportEvent)`).
