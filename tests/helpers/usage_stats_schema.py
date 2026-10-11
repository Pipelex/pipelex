"""Check an event pipelex builds against the vendored usage-statistics schema, as PostHog's gate would.

The schema is `tests/data/usage_stats/usage-statistics.json`, a byte-identical copy of the contract's
`conformance/specs/usage-statistics.json`. `envelope_problems` applies the gate's rules to one posted envelope: a
declared event the tool may send, the envelope fields matching their patterns, `$process_person_profile` false, every
property declared, present only when its condition holds, of its type and within its bounds or values, and every
required property present. An empty list means the gate keeps the event.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any, cast

USAGE_STATS_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "data" / "usage_stats" / "usage-statistics.json"


@cache
def load_usage_stats_schema() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(USAGE_STATS_SCHEMA_PATH.read_text(encoding="utf-8")))


def _json_type(value: object) -> str:
    """The type a JSON reader in JavaScript gives a value: a number with no fractional part is an integer."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "integer" if value.is_integer() else "float"
    if isinstance(value, str):
        return "string"
    return "other"


def _condition_holds(*, condition: dict[str, Any], properties: dict[str, Any]) -> bool:
    actual = properties.get(condition["property"])
    expected = condition["equals"]
    return _json_type(actual) == _json_type(expected) and actual == expected


def _pattern_matches(*, pattern_name: str, value: str) -> bool:
    pattern = load_usage_stats_schema()["patterns"][pattern_name]
    return len(value) <= pattern["max_length"] and re.fullmatch(pattern["regex"], value) is not None


def _value_problem(*, name: str, spec: dict[str, Any], value: object, properties: dict[str, Any]) -> str | None:
    kind = spec["type"]
    is_valid: bool
    if kind in {"integer", "number"}:
        is_number = not isinstance(value, bool) and isinstance(value, int | float)
        is_valid = is_number and spec["min"] <= cast("float", value) <= spec["max"]
        if kind == "integer":
            is_valid = is_valid and _json_type(value) == "integer"
    elif kind == "boolean":
        is_valid = isinstance(value, bool)
    elif kind == "enum":
        allowed: list[str] | None = spec.get("values")
        if allowed is None:
            selector = properties.get(spec["values_by"]["property"])
            allowed = spec["values_by"]["values"].get(selector) if isinstance(selector, str) else None
        is_valid = allowed is not None and isinstance(value, str) and value in allowed
    elif kind == "pattern":
        is_valid = isinstance(value, str) and _pattern_matches(pattern_name=spec["pattern"], value=value)
    else:
        return f"{name} is a {kind}, which no tool sends"
    if not is_valid:
        return f"invalid value for {name}: {value!r}"
    fixed_when: dict[str, Any] | None = spec.get("fixed_when")
    if fixed_when is not None and _condition_holds(condition=fixed_when, properties=properties) and value != fixed_when["value"]:
        return f"{name} must be {fixed_when['value']!r} when {fixed_when['property']} is {fixed_when['equals']!r}"
    return None


def declared_properties(*, event_name: str) -> dict[str, dict[str, Any]]:
    """Every property an event may carry: the common ones when it carries them, then its own."""
    schema = load_usage_stats_schema()
    event_spec = schema["events"][event_name]
    declared: dict[str, dict[str, Any]] = {}
    if event_spec["common"]:
        declared.update(schema["common_properties"])
    declared.update(event_spec["properties"])
    return declared


def envelope_problems(*, envelope: dict[str, Any]) -> list[str]:
    """What PostHog's gate would refuse in one posted envelope; empty when it keeps the event."""
    schema = load_usage_stats_schema()
    event_name = envelope.get("event")
    if not isinstance(event_name, str) or event_name not in schema["events"]:
        return [f"undeclared event {event_name!r}"]
    problems: list[str] = []
    allowed_keys = {"event", "properties", *schema["envelope"]["fields"]}
    for key in envelope:
        if key not in allowed_keys:
            problems.append(f"the envelope carries {key}, which no sender sets")
    for field_name, field in schema["envelope"]["fields"].items():
        field_value = envelope.get(field_name)
        if not isinstance(field_value, str) or not _pattern_matches(pattern_name=field["pattern"], value=field_value):
            problems.append(f"envelope field {field_name} is not a {field['pattern']}: {field_value!r}")
    raw_properties = envelope.get("properties")
    if not isinstance(raw_properties, dict):
        return [*problems, "properties are not an object"]
    properties = cast("dict[str, Any]", raw_properties)
    person_profile_property: str = schema["person_profile_property"]
    if properties.get(person_profile_property) is not False:
        problems.append(f"{person_profile_property} must be false")
    event_spec = schema["events"][event_name]
    if properties.get("tool") not in event_spec["tools"]:
        problems.append(f"tool {properties.get('tool')!r} may not send {event_name}")
    declared = declared_properties(event_name=event_name)
    for name, value in properties.items():
        if name == person_profile_property:
            continue
        spec = declared.get(name)
        if spec is None:
            problems.append(f"undeclared property {name}")
            continue
        if value is None:
            problems.append(f"{name} is null; an optional property is left out")
            continue
        when: dict[str, Any] | None = spec.get("when")
        if when is not None and not _condition_holds(condition=when, properties=properties):
            problems.append(f"{name} is not allowed here")
            continue
        value_problem = _value_problem(name=name, spec=spec, value=value, properties=properties)
        if value_problem is not None:
            problems.append(value_problem)
    for name, spec in declared.items():
        if not spec["required"] or properties.get(name) is not None:
            continue
        when = spec.get("when")
        if when is None or _condition_holds(condition=when, properties=properties):
            problems.append(f"missing required {name}")
    return problems


def assert_envelope_is_valid(envelope: dict[str, Any]) -> None:
    problems = envelope_problems(envelope=envelope)
    assert not problems, f"The gate would drop this {envelope.get('event')}: {problems}\n{json.dumps(envelope, indent=2)}"
