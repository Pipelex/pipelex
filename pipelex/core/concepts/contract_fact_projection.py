"""Contract facts projected into what enforces and describes a value: a pydantic annotation and a JSON Schema.

A field's or a slot's constraints are enforced wherever the runtime validates the value's type, and every fact reaches the
JSON Schema of each slot that holds it (spec: mthds-format.md, "Contract Facts"; pipe-io-contracts.md, "The Input Schema").
Two projections of the same facts:

- `constrained_annotation`, which wraps an annotation so validating a value enforces the site's constraints and the class's
  JSON Schema states every fact. The pattern is enforced with Python's `re`, the engine the language check compiles it with,
  rather than the schema engine pydantic defaults to, which reads fewer constructs. A site typed by a concept constrains the
  value the concept carries, the `number` of a `Number` or the `text` of a `Text`.
- `fact_json_schema`, the JSON Schema keywords of a site's facts: the four bounds, the lengths, `pattern`, `format`, the
  option values as `enum`, and `examples` as an annotation. `unit` and `aggregate` have no JSON Schema keyword.
"""

import copy
import datetime
from collections.abc import Mapping
from typing import Annotated, Any, cast

from pydantic import AfterValidator, Field, GetCoreSchemaHandler
from pydantic.dataclasses import dataclass
from pydantic_core import CoreSchema

from pipelex.core.stuffs.number_content import NumberContent
from pipelex.core.stuffs.stuff_content import StuffContent
from pipelex.core.stuffs.text_content import TextContent
from pipelex.language.contract_facts import ContractFactKey, constraint_break_message, json_example, shown_value

_JSON_SCHEMA_KEYWORDS: dict[ContractFactKey, str] = {
    ContractFactKey.MINIMUM: "minimum",
    ContractFactKey.MAXIMUM: "maximum",
    ContractFactKey.EXCLUSIVE_MINIMUM: "exclusiveMinimum",
    ContractFactKey.EXCLUSIVE_MAXIMUM: "exclusiveMaximum",
    ContractFactKey.MIN_LENGTH: "minLength",
    ContractFactKey.MAX_LENGTH: "maxLength",
    ContractFactKey.PATTERN: "pattern",
    ContractFactKey.FORMAT: "format",
}


def fact_json_schema(*, facts: Mapping[str, Any], choice_values: list[str] | None = None) -> dict[str, Any]:
    """The JSON Schema keywords of a site's facts and options, in the standard's key order, absent facts absent."""
    schema: dict[str, Any] = {}
    for key, keyword in _JSON_SCHEMA_KEYWORDS.items():
        if key in facts:
            schema[keyword] = facts[key]
    if choice_values is not None:
        schema["enum"] = list(choice_values)
    examples = facts.get(ContractFactKey.EXAMPLES)
    if isinstance(examples, list):
        schema["examples"] = [json_example(value=example) for example in examples]  # pyright: ignore[reportUnknownVariableType]
    return schema


def carried_value(*, value: Any) -> Any:
    """The plain value a value of a concept-typed site carries: the number of a `Number`, the text of a `Text`, or the value
    itself for a site typed by a field type. A date or a time carries no constrainable value, since only examples apply to
    them. A stored text is read from its loaded value; one never loaded carries nothing readable here, so the input gate
    loads every stored value it checks first and refuses one it still cannot read.
    """
    if isinstance(value, NumberContent):
        return value.number
    if isinstance(value, TextContent):
        return value.require_value() if value.is_loaded else None
    if isinstance(value, StuffContent):
        return None
    return value


def carried_field_name(*, value: Any) -> str:
    """The name of the field of a stuff content holding the value its slot's facts constrain: `number` or `text`."""
    if isinstance(value, NumberContent):
        return "number"
    return "text"


def contract_break(*, value: Any, facts: Mapping[str, Any], choice_values: list[str] | None = None) -> str | None:
    """Why a value breaks a site's constraints or options, as a sentence, or `None` when it breaks none."""
    plain = carried_value(value=value)
    if plain is None:
        return None
    if choice_values is not None and isinstance(plain, str) and plain not in choice_values:
        return f"{shown_value(value=plain)} is not one of the options {choice_values}"
    return constraint_break_message(value=plain, facts=facts)


@dataclass(frozen=True, eq=False)
class ContractFactsMetadata:
    """The facts of a constrained annotation, carried in its metadata for what builds a value of it rather than validates one:
    the dry run's mock factory reads them to make a value that honours them (`pipelex.cogt.content_generation.contract_fact_mocks`).
    Pydantic ignores metadata it does not know, so carrying them changes neither validation nor the JSON Schema.

    `eq=False` keeps identity equality and hashing: `typing` hashes an annotation's metadata when it builds a union over it
    (`Annotated[...] | None`), and the facts, a dict that may hold a list of examples, cannot be hashed.
    """

    facts: dict[str, Any]


def contract_facts_of(*, metadata: list[Any] | tuple[Any, ...]) -> dict[str, Any] | None:
    """The facts a constrained annotation's metadata carries, or `None` when it carries none: the runtime class's
    `ContractFactsMetadata`, or the `ContractFacts` a generated `python-structures` class spells them with.
    """
    for item in metadata:
        if isinstance(item, ContractFactsMetadata | ContractFacts):
            return item.facts
    return None


def constrained_annotation(*, annotation: Any, facts: Mapping[str, Any], states_schema: bool = True) -> Any:
    """An annotation whose validation enforces the site's constraints and whose JSON Schema states every fact.

    Returned unchanged for a site authoring no fact, so a structure with none builds the class it built before. A site
    typed by a field type takes pydantic's own constraints, which its JSON Schema states and the dry run's mock factory
    honours: the bounds and the lengths. `pattern` and `format` are asserted by a validator, with the judgment the input
    gate applies (`constraint_break_message`), and the schema carries both keywords: a pattern is searched with a time
    limit (`search_pattern`), which pydantic's own `pattern` constraint, searched with Python's `re` without bound, would
    not keep. The examples ride the field's own `examples`.

    A site typed by a concept (`states_schema` false) enforces its facts on the value its concept carries, while its
    schema stays the concept's reference: the facts go onto the value's own property where a slot's schema is assembled
    (`pipelex.pipeline.pipe_io_contracts`), never beside a `$ref`.
    """
    if not facts:
        return annotation
    frozen_facts = dict(facts)

    def enforce(  # kw-only: ignore (pydantic calls an AfterValidator positionally)
        value: Any,
    ) -> Any:
        message = contract_break(value=value, facts=frozen_facts)
        if message is not None:
            raise ValueError(message)
        return value

    facts_metadata = ContractFactsMetadata(facts=frozen_facts)
    if not states_schema:
        return Annotated[annotation, AfterValidator(enforce), facts_metadata]
    constraints: dict[str, Any] = {
        "ge": frozen_facts.get(ContractFactKey.MINIMUM),
        "le": frozen_facts.get(ContractFactKey.MAXIMUM),
        "gt": frozen_facts.get(ContractFactKey.EXCLUSIVE_MINIMUM),
        "lt": frozen_facts.get(ContractFactKey.EXCLUSIVE_MAXIMUM),
        "min_length": frozen_facts.get(ContractFactKey.MIN_LENGTH),
        "max_length": frozen_facts.get(ContractFactKey.MAX_LENGTH),
    }
    examples = frozen_facts.get(ContractFactKey.EXAMPLES)
    if isinstance(examples, list):
        constraints["examples"] = [json_example(value=example) for example in cast("list[Any]", examples)]
    field_info = Field(**{key: value for key, value in constraints.items() if value is not None})
    # The facts a validator asserts, after pydantic's own bounds and lengths, in the standard's order: `pattern`, `format`.
    asserted_facts: dict[str, Any] = {
        key: frozen_facts[key] for key in (ContractFactKey.PATTERN, ContractFactKey.FORMAT) if frozen_facts.get(key) is not None
    }
    if not asserted_facts:
        return Annotated[annotation, field_info, facts_metadata]

    def enforce_asserted(  # kw-only: ignore (pydantic calls an AfterValidator positionally)
        value: Any,
    ) -> Any:
        message = contract_break(value=value, facts=asserted_facts)
        if message is not None:
            raise ValueError(message)
        return value

    stated_keywords: dict[str, Any] = {_JSON_SCHEMA_KEYWORDS[ContractFactKey(key)]: str(value) for key, value in asserted_facts.items()}
    return Annotated[annotation, field_info, AfterValidator(enforce_asserted), Field(json_schema_extra=stated_keywords), facts_metadata]


def _example_as_object(*, example: Any, property_name: str) -> Any:
    """An example of a date-valued or time-valued slot as the stuff content its schema describes (round-2 rule H)."""
    if isinstance(example, datetime.datetime):
        return {"date": example.date().isoformat(), "time": example.timetz().isoformat()}
    if isinstance(example, datetime.date):
        return {"date": example.isoformat()}
    if isinstance(example, datetime.time):
        return {property_name: example.isoformat()}
    return json_example(value=example)


def _content_schema(*, schema: dict[str, Any]) -> dict[str, Any]:
    """The object schema of one stuff content: the items of a list's schema, through a top-level `$ref` into `$defs`."""
    target = schema
    items = target.get("items")
    if target.get("type") == "array" and isinstance(items, dict):
        target = cast("dict[str, Any]", items)
    reference = target.get("$ref")
    definitions = schema.get("$defs")
    if isinstance(reference, str) and isinstance(definitions, dict):
        definition = cast("dict[str, Any]", definitions).get(reference.rsplit("/", 1)[-1])
        if isinstance(definition, dict):
            target = cast("dict[str, Any]", definition)
    return target


def _value_branches(*, value_schema: dict[str, Any]) -> list[dict[str, Any]]:
    """The branches of a value property that hold the value itself: every non-null `anyOf` arm when it has several, such as
    the `integer` and `number` arms of a `Number`, so a value matching any arm meets the facts, and never the null arm (the
    `text` of a stored `Text` is null), so the facts never refuse it. The property itself when it has no `anyOf`.
    """
    branches = value_schema.get("anyOf")
    if isinstance(branches, list):
        value_branches = [
            cast("dict[str, Any]", branch)
            for branch in cast("list[Any]", branches)
            if isinstance(branch, dict) and cast("dict[str, Any]", branch).get("type") != "null"
        ]
        if value_branches:
            return value_branches
    return [value_schema]


def slot_schema_with_facts(*, json_schema: dict[str, Any], facts: Mapping[str, Any], choice_values: list[str] | None) -> dict[str, Any]:
    """A slot's input JSON Schema with its contract facts and options stated on the value its concept carries.

    The schema is copied, never changed in place, since the bare concept's schema is shared between slots. A text-valued
    slot states its facts and options on `text`, a number-valued one on `number`. A date-valued or time-valued slot has no
    constraint, and its examples are stated on the content object as `{"date": …}`, `{"date": …, "time": …}` or `{"time":
    …}`. A slot authoring nothing returns the schema it was given.
    """
    if not facts and choice_values is None:
        return json_schema
    projected = copy.deepcopy(json_schema)
    content = _content_schema(schema=projected)
    properties = content.get("properties")
    if not isinstance(properties, dict):
        return projected
    typed_properties = cast("dict[str, Any]", properties)
    examples = facts.get(ContractFactKey.EXAMPLES)
    for property_name in ("number", "text"):
        value_schema = typed_properties.get(property_name)
        if isinstance(value_schema, dict):
            for value_branch in _value_branches(value_schema=cast("dict[str, Any]", value_schema)):
                value_branch.update(fact_json_schema(facts=facts, choice_values=choice_values))
            return projected
    for property_name in ("date", "time"):
        if property_name in typed_properties and isinstance(examples, list):
            content["examples"] = [_example_as_object(example=example, property_name=property_name) for example in cast("list[Any]", examples)]
            return projected
    return projected


class ContractFacts:
    """A field's contract facts as the `python-structures` codegen projection writes them: `Annotated[str, ContractFacts({...})]`.

    The generated class validates and describes the field exactly as the class the runtime builds for the same concept
    (`pipelex.core.concepts.structure_generation`), since pydantic builds the field from `constrained_annotation` over the
    annotated type. `carried` is true on a field typed by a concept, whose facts constrain the value the concept carries
    (the `number` of a `Number`, the `text` of a `Text`) rather than the field's own value.

    A plain class, hashed by identity: `typing` hashes an annotation's metadata when it builds a union over it
    (`Annotated[...] | None`), and the facts, a dict that may hold a list of examples, cannot be hashed.
    """

    __slots__ = ("carried", "facts")

    def __init__(self, facts: dict[str, Any], *, carried: bool = False) -> None:
        self.facts = dict(facts)
        self.carried = carried

    def __get_pydantic_core_schema__(self, source_type: Any, handler: GetCoreSchemaHandler) -> CoreSchema:  # ruff: ignore[bad-dunder-method-name]
        return handler.generate_schema(constrained_annotation(annotation=source_type, facts=self.facts, states_schema=not self.carried))
