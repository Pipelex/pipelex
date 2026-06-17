# Suspects — package `runtime_bridge`

Reviewed: 12 Section A + 0 primitive lone-subjects. Suspects: 1.

## High confidence

_(none)_

## Medium / low confidence

- `pipelex/runtime_bridge/primitives/hydration.py:17` — `_validate_as_known_class` — `def _validate_as_known_class(item_class: type[StuffContent], *, raw_item: StuffContent | dict[str, Any]) -> StuffContent` — `item_class` is a type/schema used to validate, not the data being acted on; `raw_item` is the actual object being processed. The function "validates raw_item into item_class", so `raw_item` is arguably the semantic subject. Call sites read `_validate_as_known_class(item_class_or_none, raw_item=raw_item)` which is passable but unusual (a type as the positional subject). — suggested fix: `def _validate_as_known_class(*, item_class: type[StuffContent], raw_item: StuffContent | dict[str, Any]) -> StuffContent` (fully keyword-only) or reorder to `def _validate_as_known_class(raw_item: ..., *, item_class: ...)`.
