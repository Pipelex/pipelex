# Suspects — package `observer`

Reviewed: 1 Section A + 1 primitive lone-subject. Suspects: 2.

## High confidence

- `pipelex/observer/multi_observer.py:14` — `MultiObserver.remove_observer` — `def remove_observer(self, name: str) -> None` — Asymmetric with `add_observer(*, name, observer)` which is already fully keyword-only; `remove_observer("some_name")` passes a bare string with no keyword context at the call site. Convention consistency and readability both point toward `def remove_observer(self, *, name: str) -> None`.

- `pipelex/observer/local_observer.py:22` — `LocalObserver._write_to_jsonl` — `def _write_to_jsonl(self, event_type: str, *, payload: PayloadType) -> None` — `event_type` is a routing/selector string (determines which file to write to and which key to inject into the payload), not the semantic object being written. The payload is the real subject. Call sites pass a named constant (`LocalObserverEventType.BEFORE_RUN`) so readability is acceptable, but the two-parameter shape (`event_type` positional, `payload` keyword) is inconsistent: both parameters are equally descriptive options that label different aspects of the write operation, and `_write_to_jsonl(*, event_type, payload)` would self-document the call site more clearly.
