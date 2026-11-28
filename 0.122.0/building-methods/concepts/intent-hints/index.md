# Intent Hints

Intent hints let a method author state, in the method itself, how a value is *meant to be presented* — that a text is flowing prose rather than a short label, that a number is a subjective rating rather than a measured quantity. They are part of the MTHDS standard (spec: `intent-hints.md` in the MTHDS spec) and they are strictly **non-normative**: hints never change what a pipe accepts, produces, or validates. They travel through the library crate and surface on the input-form descriptor, where a form renderer can honor them.

## Authoring

A `hints` table is a flat table of string keys to string values. The standard defines three keys, each with a closed vocabulary: `intent` says what kind of value a site holds, `role` what an input is to the method, and `part` what a field is to its record.

| `intent` | Applies to | Declares |
|---|---|---|
| `prose` | text-valued sites | Flowing natural language, written and read as running text. |
| `label` | text-valued sites | A short designation — a name, a title; a few words on one line. |
| `code` | text-valued sites | Source code or another formal text a machine reads, where every character counts. |
| `identifier` | text-valued sites | A short reference that names one thing exactly, such as an order number, copied rather than written. |
| `question` | text-valued sites | A request addressed to the method, in the person's own words. |
| `rating` | number-valued sites | A subjective score on a scale — a judgment, not a measurement. |
| `quantity` | number-valued sites | An amount — a count or a measured magnitude. |
| `photo` | image-valued sites | A picture taken of the world with a camera. |
| `screenshot` | image-valued sites | A capture of a screen. |
| `scan` | image-valued and document-valued sites | A paper document captured by a scanner or a camera. |

`role` sits on an input slot and says how often a person changes that input:

| `role` | The input is |
|---|---|
| `subject` | the material the method works on, given on every run |
| `context` | a fact about this case, such as the counterparty's name |
| `guidance` | how the person wants the work done, such as "focus on liability" |
| `reference` | the yardstick the method applies, set once and reused: a playbook, a checklist |
| `setting` | a choice with a sensible default, such as the output language |

`part` sits on a structure field and says what the field is to the record a reader looks at:

| `part` | The field is | Applies to |
|---|---|---|
| `title` | the words that name the record | a text-valued field, held once per record |
| `summary` | the record in one or two sentences | a text-valued field, held once per record |
| `verdict` | the answer the reader came for | an enumeration, `boolean` or number-valued field, or a `YesNo`, `Choice` or `Rating` concept field, held once per record |
| `metric` | a headline number that is not the verdict | a number-valued field |
| `body` | the main content to read | any field |
| `evidence` | what supports the verdict | any field |
| `detail` | anything else worth showing | any field |

Hints attach at three sites:

**On a concept:**

```toml
[concept.Essay]
description = "A short essay"
hints = { intent = "prose" }
```

**On a structure field:**

```toml
[concept.Review.structure]
headline = { type = "text", description = "the headline", hints = { intent = "label" } }
stars = { type = "integer", description = "the stars", hints = { intent = "rating" } }
```

**On a pipe input slot**, using the expanded slot form — `concept` carries exactly the grammar the plain string form does, markers included:

```toml
[pipe.write_review]
type = "PipeLLM"
description = "Write a review"
inputs = { topic = { concept = "Text", hints = { intent = "prose" } }, refs = { concept = "Reference[]", hints = { intent = "label" } } }
output = "Review"
prompt = "Write a review of @topic"
```

A slot table with no `hints`, `description`, contract fact or `choices` is the same slot as the plain string: `x = { concept = "Text" }` and `x = "Text"` parse to identical blueprints and hash identically in the crate.

## Shape is strict, content is lenient

The *shape* of a `hints` table is enforced: it must be a flat string-to-string table, and the expanded slot form admits only `concept`, `hints`, `description`, the [contract facts](inline-structures.md#contract-facts) and `choices` — anything else (a non-table `hints`, a number value, a nested table, an unknown slot-table key like `placeholder`) is a structural validation error.

The *content* is lenient: an unknown hint key or an unknown `intent` word parses, is preserved through the crate and onto the descriptor, and is only **warned** about. Validation emits advisory warnings (never errors) on the report's `warnings` array, each naming its site: an unknown hint key (`hint_unknown_key`), an unknown `intent`, `role` or `part` word (`hint_unknown_intent`, `hint_unknown_role`, `hint_unknown_part`), a known word on a site it does not apply to (`hint_inapplicable_intent`, `hint_inapplicable_role`, `hint_inapplicable_part`) — for example `rating` on a text field, or `role` on a structure field — and a `part` held once per record (`title`, `summary`, `verdict`) that two fields of one structure claim (`hint_duplicate_part`). This is what lets the vocabulary grow between standard versions without breaking older validators.

## Precedence and inheritance

Effective hints merge **key by key**, and a nearer declaration wins:

- Along a refinement chain, a refining concept's hints override its base's, key by key; keys the refiner does not set are inherited. A hint can be overridden but never cleared.
- At a site, the site's hints (a field's, a slot's) win over the concept's effective hints, key by key.

```toml
[concept.Badge]
description = "A badge"
hints = { intent = "label" }

[concept.SpecialBadge]
description = "A special badge"
refines = "Badge"
hints = { intent = "prose" }   # overrides the inherited label
```

## Where hints surface

Hints ride the library crate (a concept's effective hints are assembled during normalization; field and slot hints travel as authored) and land on the [input-form descriptor](../../under-the-hood/input-form-descriptor.md): every node's `hints` slot carries its final effective merge, and an applicable `intent` word feeds the node's `kind` — `prose` and `label` select between the `prose` and `text` kinds on text-valued nodes; `rating` and `quantity` ride the slot for the renderer without changing `kind`. On a plural site (a `Concept[]` slot, a list field), applicability is judged per item, and the merged hints appear on both the `list` node and its `item`.

Because hints are non-normative, the runtime never reads them: execution, validation verdicts, and pipe contracts are identical with and without them — and a method that authors no hints keeps its crate fingerprint, byte for byte.

## Related Documentation

- [Refining Concepts](refining-concepts.md) - How hints inherit along a refinement chain
- [Inline Structures](inline-structures.md) - Attaching hints to a structure field
- [Designing Pipelines](../pipes/index.md#understanding-the-pipe-contract) - The expanded input slot form
- [Input-Form Descriptor](../../under-the-hood/input-form-descriptor.md) - Where effective hints surface for a renderer
