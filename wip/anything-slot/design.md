---
status: draft
item: L-260902-10eb56
---

# What an `Anything` or `JSON` input slot takes, and how the rest of the shaper's fallback refuses

`native.Anything` is the concept the MTHDS standard defines as the untyped vehicle: structureless by design, "accepts any type". Its published input contract already says so — a permissive JSON Schema and the fill-in template `{"concept": "native.Anything", "content": {}}` — but the input shaper does not honour it. This document verifies the bug, rules on what an `Anything` slot takes and what stuff it produces, and rules jointly on the two sibling items the ledger asked to have decided together.

The same fallback path also breaks `native.JSON` slots, and it refuses everything else it cannot read without naming the slot, which a later report ran into: "one input was a list of plain JSON objects … most likely an Anything or dynamic slot". So the design also gives `JSON` a handler of its own whose compact template is the bare object (R7), and makes the fallback's remaining refusals typed input errors that name the input and its declared concept (R8). It rules on an envelope-shaped item inside an `Anything[]` or `JSON[]` list (R10), and on how the docs teach the choice among the untyped concepts (R11). And because a value that goes in has to come back out, it rules on the wire form of an `Anything` value on the output side too (R9), which is built under its own items rather than here. The build is in `plan.md` beside it.

## Verification

The bug is confirmed on `dev` at `be796a0d8`, and it is wider than filed. Measured through `pipelex.kernel.memory_ops.shape_inputs`, the entry point an entry-pipe run uses, with a `PipeCompose` declaring `inputs = { anything_in = "Anything" }` and a second declaring `inputs = { items = "Anything[]" }`:

```
== carry (anything_in)
  bare {}                    REFUSED StuffFactoryError: ... does not have a 'concept' key.
  bare string                OK      -> concept=native.Text content=TextContent
  bare number                REFUSED StuffFactoryError: Unexpected type for stuff_content_or_data: <class 'int'>
  bare float                 REFUSED StuffFactoryError: Unexpected type for stuff_content_or_data: <class 'float'>
  bare bool                  REFUSED StuffFactoryError: Unexpected type for stuff_content_or_data: <class 'bool'>
  bare list                  REFUSED StuffFactoryError: Cannot create Stuff from list of <class 'int'>
  bare dict                  REFUSED StuffFactoryError: ... does not have a 'concept' key.
  envelope {}                REFUSED StuffFactoryError: ... 'Anything' is not compatible with a dict content
  envelope str               REFUSED StuffFactoryError: ... 'Anything' is not compatible with native concept 'native.Text', ...
  envelope num               REFUSED StuffFactoryError: Unexpected type for content value: <class 'int'>
  envelope list              REFUSED StuffFactoryError: Cannot create Stuff from list of <class 'int'> in content
  envelope native.Text       REFUSED ExplicitConceptIncompatibleError: ... declares concept 'native.Anything', but you provided a value typed as 'native.Text'
  envelope native.JSON       REFUSED ExplicitConceptIncompatibleError: ... typed as 'native.JSON' ...
  envelope Question          REFUSED ExplicitConceptIncompatibleError: ... typed as 'anything_probe.Question' ...
== carry_list (items)
  bare [{}]                  REFUSED StuffFactoryError: Cannot create Stuff from list of <class 'dict'>
  bare [str]                 OK      -> concept=native.Text content=ListContent
  bare [1,2]                 REFUSED StuffFactoryError: Cannot create Stuff from list of <class 'int'>
  bare []                    REFUSED StuffFactoryError: Cannot create Stuff 'items' from empty list
  envelope [{}]              REFUSED ValidationError: 1 validation error for TextContent (raw pydantic, untyped)
```

Three things the item did not record:

- **A typed envelope is refused too.** `{"concept": "Text", "content": "hi"}`, a `native.JSON` envelope and a user concept are all refused with `ExplicitConceptIncompatibleError`. The cause is `ConceptLibrary.is_compatible(tested=X, wanted=native.Anything)`, which answers `False` for every `X` but `Anything` itself: the declaration tier (`Concept.are_compatible_by_declaration`, `pipelex/core/concepts/concept.py`) has no rule for it, and the class tier bails out because `Anything` declares no class. So the one spelling that names its type explicitly — D6's escape hatch — cannot reach an `Anything` slot at all.
- **The same compatibility gap refuses a valid bundle at validation time.** A `PipeSequence` declaring `output = "Anything"` over a last step producing `Text` fails to validate: `PipeSequence concept mismatch: the output concept 'native.Text' of the last step 'echo' of sequence pipe 'seq' is not compatible with the output concept 'native.Anything' of the sequence.` (`pipelex/pipe_controllers/sequence/pipe_sequence.py`, the `is_compatible` check in its output validation).
- **`Anything[]` ignores its multiplicity.** The `DYNAMIC` arm returns before `_shape_with_multiplicity`, so a legal empty list is refused, a fixed count is never checked and a single value is never wrapped — Gap B of `wip/inputs/input-shaper-multiplicity-gaps.md`, still open for both `Dynamic` and `Anything`. The `[{}]` envelope escapes as a raw pydantic `ValidationError`, because Case 2.6 of the bottom-up factory falls back to `TextContent` for an item class it cannot resolve.

The root cause is the one the item names: `resolve_input_kind` sends `Anything` down the `DYNAMIC` arm, which hands the raw value to the bottom-up `StuffFactory`, and that factory infers a concept from the value's shape without consulting the declared one. It has no arm for a number, a boolean, a bare object or a list of non-strings, and its envelope arm looks up `AnythingContent` in the class registry and finds nothing.

**The list-of-objects report, reproduced.** The report pointed at the `DYNAMIC` call in `_shape_one` (`input_shaper.py`, line 188 on `dev` at `d93a24767`) and the bottom-up factory's `Cannot create Stuff from list of <class 'dict'>` (`stuff_factory.py`, line 454), without naming the slot. That is because the refusal names neither the input nor its declared concept. Sending `[{"a": 1}, {"b": 2}]` to every slot kind that reaches the fallback gives the same error at eleven of them: `Anything`, `Anything[]`, `Dynamic`, `Dynamic[]`, `JSON`, `JSON[]`, `Composite[]`, `Html[]`, `TextAndImages[]`, `SearchResult[]` and `Page[]`. A user concept with a structure, `Record[]`, takes the same list. `StuffFactoryError` declares no error domain, so the refusal is not even classified as the caller's input fault.

**A `JSON` slot is broken in both directions.** Measured on the same `dev`:

```
JSON     hi                       OK      concept=native.Text content=TextContent(text='hi')
JSON     ['a', 'b']               OK      concept=native.Text content=ListContent(items=[TextContent(text='a'), TextContent(text='b')])
JSON     {'a': 1}                 REFUSED StuffFactoryError: Trying to create a Stuff 'x' from a dict ... does not have a 'concept' key.
JSON     {'json_obj': {'a': 1}}   REFUSED StuffFactoryError: (same)
JSON     3                        REFUSED StuffFactoryError: Unexpected type for stuff_content_or_data: <class 'int'>
JSON[]   hi                       OK      concept=native.Text content=TextContent(text='hi')     (not even wrapped into a list)
```

It refuses every object — the one thing a `JSON` slot is for — and quietly accepts a string as a `native.Text` stuff sitting in a slot the method declared `JSON`. Only the envelope, `{"concept": "native.JSON", "content": {"json_obj": {…}}}`, works today.

**What the runtime already does with an `Anything` stuff.** No arm has to be invented downstream. `PipeBatch` stamps the slot's *declared* concept onto the stuffs it builds — each item stuff takes the input spec's concept and each aggregate takes the batch's output concept (`pipelex/pipe_controllers/batch/pipe_batch.py`, the two `StuffFactory.make_stuff` calls) — so a batch over `Anything[]` already produces stuffs whose concept is `native.Anything` and whose contents are concrete. `PipeParallel` guards `declares_a_structure_class` on a branch stuff's concept for the same reason. Measured by handing the runner a pre-built working memory: a `native.Anything` stuff holding a `JSONContent`, a `TextContent` or a `NumberContent` renders through `$anything_in` as `{"a": 1}`, `hi` and `4.2`, a mixed `ListContent` renders item by item, and every run result serializes.

## Rulings

### R1 — The slot keeps its declared concept; the content is the value's natural content

**A bare value at an `Anything` slot becomes a stuff whose concept is `native.Anything` and whose content is the native content its JSON type names.** Nothing is inferred beyond the JSON type, and nothing is guessed from the value's text.

| Value | Content |
| --- | --- |
| string | `TextContent` |
| number (a boolean is never a number) | `NumberContent` |
| boolean | `YesNoContent` |
| object | `JSONContent`, the object as `json_obj` — so the published template `{}` shapes into `JSONContent(json_obj={})` |
| TOML date or datetime literal (inputs files only) | `DateContent` |
| TOML time literal (inputs files only) | `TimeContent` |
| an already-built `StuffContent` object (Python callers) | the explicit arm, as today: its concept is inferred from its class and kept, per R2 and D6 |
| array | refused at a single slot (R3), shaped element-wise at a plural one |
| null | refused (R3) |
| anything else a Python caller hands in | refused as not a JSON value |

A string that looks like a URL is still text. The file-ish reading of D3 belongs to slots that declare `Image` or `Document`, and an `Anything` slot declares nothing of the kind.

Why the declared concept rather than the natural one. Every top-down arm of the shaper already stamps the declared concept (`StuffFactory.make_stuff(concept=declared_concept, …)` at the end of `_shape_one`), and `PipeBatch` does the same for `Anything` today. A stuff has exactly one concept, so inferring `native.Text` or `native.Number` breaks on the first heterogeneous `Anything[]` list, while `native.Anything` over a mixed `ListContent` is exactly what a batch already produces. And the concept a stuff carries at an `Anything` slot should say what the method declared there, not what the shaper guessed: the content class already says what the value concretely is. That last point holds in memory only. On the wire the content class is invisible, which R9 answers.

The invariant this relaxes is "the content is an instance of the concept's structure class". It becomes "…when the concept declares one", which is what `Concept.declares_a_structure_class` exists to say.

### R2 — Every concept satisfies `native.Anything`

**`Concept.are_compatible_by_declaration` answers `True` whenever the wanted concept is `native.Anything`**, right after its two dynamic short-circuits, keyed on `not concept_2.declares_a_structure_class`. The reverse stays `False`: an `Anything` value is not known to be a `Text`, and `strict=True` changes nothing, since the rule sits in the declaration tier.

Consequences, all intended:

- A typed envelope at an `Anything` slot is accepted and **keeps its explicit concept** — D6's "explicit wins when compatible", with `Anything` at the top of the lattice. `{"concept": "Image", "content": {"url": …}}` produces a `native.Image` stuff.
- A `PipeSequence` whose output is `Anything` validates over any last step.
- The rule matches the language reference ("Accepts any type") and what `pipelex` already does by special case in controller validation (`pipe_abstract.py`, the `DYNAMIC`/`ANYTHING` carve-outs) and in `PipeCondition`. The implementers' runtime guide in `mthds` narrows it to native concepts; that inconsistency is filed as L-260927-afaf62 for the standard's owner.

The sites that ask `is_compatible` with a wanted concept of `Anything` are the shaper's two compatibility checks and `PipeSequence`'s output check; every other site asks about `Text`, `Html`, `Image`, `Document`, `YesNo`, `Date` or `Time`, which this rule does not touch.

### R3 — Multiplicity is peeled for `Anything` like every typed kind; D2 and D9 hold

`Anything` leaves the `DYNAMIC` short-circuit and takes the path the typed kinds take, `_shape_with_multiplicity`, with a new per-item arm. So:

- `Anything[]` shapes element-wise, and **items may differ in JSON type**. `[]` is a legal empty list, and a single value is wrapped into a one-item list (D2).
- `Anything[N]` checks the count.
- An array at a single `Anything` slot is `ListWhereSingularError` (D2), and an item of a plural slot that is itself an array is refused as a wrong kind. A list of lists has no stuff to become.
- A top-level null is `NullInputError` (D9), whether bare or as an envelope's content, and a null item is refused as a wrong kind.

This closes Gap B of `input-shaper-multiplicity-gaps.md` for `Anything`. `Dynamic` keeps its bottom-up arm; nothing here rules on it.

### R4 — The published schema says what R3 refuses: no array and no null at an element position *(needs Louis's yes)*

**The permissive schema gains one constraint: `{"title": "native.Anything", "description": "…", "not": {"type": ["array", "null"]}}`.** `Anything[]` wraps it exactly as today, so its items exclude arrays and null too, and the standard's rule that a plural schema's items are "exactly what the same concept would carry at single" holds unchanged.

The item asked to close the gap in the shaper rather than narrow the contract to a limitation, and R4 is the one place this design narrows. It is not a limitation of the `Anything` arm, though: D2 (a single slot never holds a list) and D9 (absence is an omitted key, never a null) refuse those two shapes at *every* slot, and every other slot's schema already excludes them — an object schema admits neither an array nor a null. The permissive schema is the one exception on the wire. The standard says a machine consumer validates a payload with `json_schema` and an ordinary validator (`mthds/docs/spec/pipe-io-contracts.md`, Non-Goals), and `mthds-form` does exactly that with ajv, so leaving the schema permissive keeps a gap a client meets as a refused run after its own validation passed.

If the answer is no, R1–R3 stand unchanged and the schema stays permissive; `docs/under-the-hood/pipe-io-contracts.md` then says that the two universal rules still refuse an array or a null at a single `Anything` slot.

### R5 — The envelope spellings

- **`{"concept": "native.Anything", "content": v}` at an `Anything` slot is the bare value `v`**, shaped by R1 and R3. This is the spelling both corpus shapes publish, so it is the one the round-trip gate measures.
- **A typed envelope at an `Anything` slot** builds bottom-up as today and keeps its concept (R2).
- **An envelope naming `native.Anything` at any other slot** is refused with `ExplicitConceptIncompatibleError` before anything is built: an `Anything` is not known to satisfy anything narrower. Today that case fails inside the factory with an untyped "not compatible with a dict content".

The shaper recognizes the first case by resolving the envelope's concept through the provider it already holds, with the pipe's search scope, and by asking whether that concept declares a structure class. It does not ask the factory, which has no multiplicity awareness.

D6's collision rule is unchanged and matters more here than anywhere: an object whose keys are exactly `concept` and `content` is always read as an envelope. So a raw `Anything` value of that one shape has to be sent inside an `Anything` envelope, `{"concept": "native.Anything", "content": {"concept": …, "content": …}}`, which R5 then shapes as the bare object it holds. The content of an `Anything` envelope is raw data at every depth, the items of a list included, which is what R10 relies on.

### R6 — There is never an `AnythingContent` class; the joint ruling with the sibling items

The item asked for L-260902-9546ef and L-260902-db6d1e to be ruled on together with this one, because introducing an `AnythingContent` class would change what they are. **This design introduces none, and rules that none will be introduced.** A class would have to give the untyped vehicle a shape — a `value` field, at least — and the pinned native definition says `Anything` is structureless and that a consumer must "never invent a shape" (`mthds/docs/spec/native-concepts.md`). It would also flip `declares_a_structure_class` for `Anything`, and with it every structureless arm L-260831-8f7c8c landed: the published schema, the fill-in template and the input-form descriptor's `unknown` node.

So the two siblings keep the fix directions they already state, now settled rather than provisional:

- **L-260902-9546ef** (and L-260926-f7bb28, the same site reached with `Anything[]`, now linked to it): `pipe_llm.py` resolves the output class straight from the registry. The fix routes the lookup through the guard and decides what a `PipeLLM` produces for an `Anything` output; whatever it decides, the refusal it raises is a domained `PipelexError`, never an unregistered class.
- **L-260902-db6d1e**: `pipelex build runner` refuses an `Anything` input cleanly, since PYTHON has no class to instantiate, and `refines = "Anything"` gets the standalone field-less `StructuredContent` the cross-package arm already builds, which is what codegen already emits.

Neither is widened into this change. They share a principle with it and no code.

### R7 — A `JSON` slot takes a JSON object, top-down

**`native.JSON`, and every concept refining it, gets its own shaper handler instead of the fallback.** `resolve_input_kind` recognizes it by strict compatibility with `native.JSON`, as it does the other matrix natives, so a refining concept is built through its own class.

- **A bare object is the JSON object itself**, stored as `json_obj`: `{"a": 1}` becomes `JSONContent(json_obj={"a": 1})`. This is the reading a caller means, and the one the report needed.
- **Every bare object is read literally, `{"json_obj": {…}}` included.** That object becomes `JSONContent(json_obj={"json_obj": {…}})`, just as a bare `{"text": "hi"}` at a `Text` slot is not read as a text content. The `json_obj` mapping is the content form, and the content form travels inside the envelope, for `JSON` as for every native. There is no collision rule: one looked necessary only because the compact template taught callers the wrapped form, and the next point changes the template instead.
- **The compact template shows the bare object.** The engine's light template unwraps `json_obj` the way it unwraps `text` for `Text` and `number` for `Number`, and the reference projection and both mirrors do the same, so `JSON` leaves `OUT_OF_MATRIX_NATIVES`. A developer reading the template for a `JSON` slot sees the object they have, not a Python field name inside an envelope. The corpus's `json_in` compact bytes change in all three repos in the regeneration that already retires the two `EXPECTED_UNSHAPEABLE` entries.
- **Anything else is refused as a wrong kind**, naming "a JSON object": a string, a number, a boolean. `JSONContent` holds an object only, which the pinned native definition fixes (`json_obj`, a `dict`), so a JSON array is not a `JSON` value either. Whether the standard should widen that is open question 4 (L-260927-a8ec06); this design builds "a JSON object" and says so in every doc and error it touches.
- **Multiplicity is peeled like every typed kind.** `JSON[]` shapes each object in turn, a single object is wrapped, `[]` is legal, and an array at a single `JSON` slot is `ListWhereSingularError`, whose detail already names `JSON[]` as the declaration to change.
- **The envelope is unchanged**: its content is still `JSONContent`'s field mapping, `{"json_obj": {…}}`, built bottom-up and compatibility-checked as today. The published `json_schema` describes that content form, as it does for every native (`Text`'s is `{"text": …}`), so it does not change either, and neither does codegen's `JSON` type.

The `Anything` handler's object row (R1) and this handler build the same content, so they share the code that turns an object into a `JSONContent`.

### R8 — The fallback's remaining refusals are typed input errors that name the slot

After R1 and R7, the bottom-up fallback still serves `Dynamic`, `Composite`, `Html`, `Page`, `TextAndImages`, `SearchResult`, and any user concept whose content class is not a structured one, such as a refinement of `Html`. It keeps reading a bare value by its own shape; what changes is how it refuses one. **A `StuffFactoryError` raised on that path is re-raised as a `StructureValidationError`** — an `InputShapingError`, `input`-domained and caller-facing — carrying the input name, the declared concept, the expected shape rendered from the signature, and a reason the shaper writes itself: what the value is, and that a slot of this concept reads a bare value by its own shape and has no reading for this one. The factory's own message, with its `typing.Union[…]` spelling of the accepted types, stays on the chain as the cause and out of the text a caller reads.

**The refusal's user action names the fix on the method author's side**: declare the input as `JSON` or `JSON[]` when the value is plain JSON data, or as a concept with a structure. The person who sent a list of plain JSON objects to a `Dynamic[]` slot is usually also the person who declared it, and the declaration is what should change. This mirrors `ListWhereSingularError`, whose detail already says "or declare it as a list ('X[]') in the method". The refusal does not suggest an envelope. An envelope helps only a caller who knows a concept both compatible with the slot and able to hold the value, and at a `Dynamic` slot the obvious one, `Dynamic` itself, silently drops an object's content (L-260927-bea35e).

`StructureValidationError` already has the right message form ("Input 'x' could not be built as 'native.Dynamic': …") and a page of its own, so no new error class and no change to the error identity snapshot are needed. Its `make` hard-codes the user action's detail, so it gains a way to pass this one; its docstring widens to cover this case. The explicit arm's untyped escapes are not part of R8: they are L-260831-1e1a71, which already owns them.

### R9 — On the output side, an `Anything` stuff's content is its plain JSON value *(built under L-260927-da1b09 and L-260927-223013)*

R1 keeps the declared concept and relies on the content class to say what the value is. That holds in memory, but a stuff's wire form carries only `concept` and `content`, and the content is dumped as its class's fields. Measured by dumping a `PipeOutput` holding `native.Anything` stuffs:

```
string  {"concept": "native.Anything", "content": {"text": "hi"}}
object  {"concept": "native.Anything", "content": {"json_obj": {"text": "hi"}}}
number  {"concept": "native.Anything", "content": {"number": 4.2}}
list    {"concept": "native.Anything", "content": {"items": [{"text": "a"}, {"number": 1}, {"json_obj": {"k": 1}}]}}
```

A consumer can decode that only by guessing Pipelex's content field names, which is exactly the shape-sniffing the projections refuse to do. And once R1 and R5 land, a value changes type between two methods: a bare `"hi"` comes back as `{"text": "hi"}`, and the standard's `--with-memory` chaining feeds that into the next method's `Anything` slot, where R5 reads it as the object `{"text": "hi"}`.

**The public wire form of an `Anything` stuff's content is its plain JSON value**: a `TextContent` is its string, a `NumberContent` its number, a `YesNoContent` its boolean, a `JSONContent` its object, a `DateContent` or `TimeContent` its ISO string, a `ListContent` the array of its items' values. Any other content class, such as a Python caller's `ImageContent` inside an `Anything[]` list, keeps its content form. A date comes back as a string, the one lossy case, since JSON has no date type. This is what the standard already implies, since a stuff's content is "the value, shaped as the concept's structure dictates" and `Anything` has no structure, and L-260927-223013 asks `mthds` to say it outright. The internal serialization (kajson, Temporal payloads) keeps content classes, because the runtime must restore them exactly; only the public projections change.

This is not built here. It changes the run result, the CLI's outputs and what the app and SDKs display, which is its own review, and it has its own test: a round trip through `--with-memory` that must return every R1 value unchanged. L-260927-da1b09 carries it, blocked by this item because its round trip needs R1 and R5.

### R10 — An envelope-shaped item of a bare `Anything[]` or `JSON[]` list is refused

D6's collision rule reads an object whose keys are exactly `concept` and `content` as an envelope, but only at the top of a slot (`InputShaper._is_explicit`). An item of a list reaches `_build_item_content`, which recognizes an already-built `StuffContent` object and nothing else. So under R1 and R7 as first written, `[{"concept": "Image", "content": {…}}, "caption"]` at `Anything[]` would have shaped its first item into a `JSONContent` holding the envelope, silently accepting one spelling with two meanings depending on where it sits.

**Such an item is refused as a wrong kind**, and the message says that one envelope around the whole list is how to type a list. Every other list kind already refuses it: at `Text[]` it is not a string, and at a structured concept's list it fails the structure. Two escapes stay open, both reusing an existing rule. A list of values of one concept travels in one typed envelope around the whole list. A list whose items genuinely are raw objects keyed `concept` and `content` travels inside an `Anything` envelope, whose content is raw data at every depth (R5), or, for `JSON[]`, inside a `JSON` envelope, whose items are content forms.

### R11 — The docs teach one choice among the untyped concepts, and lead with naming the JSON

After this change, three natives mean "no declared structure", each with its own rules: `Anything`, `JSON` and `Dynamic`. The docs so far describe each in its own section, so an author, human or agent, gets no rule for choosing. They get one, in this order:

1. **Data you already have as JSON objects: name it.** A concept that refines `JSON`, such as `concept.Order` with `refines = "JSON"` and a plain-language description, takes the object exactly as the developer has it, with no data model to rebuild (R7 builds it through its own class), while its name and description give an agent or a reader the meaning a bare `JSON` withholds. `tests/e2e/pipelex/pipes/pipe_operators/pipe_llm/pipe_llm_json_concept.mthds` already does it on the output side with `VectorIndex`. Fields come later, when validation is wanted, by turning it into a concept with a structure.
2. **`JSON` or `JSON[]`** when the data has no name worth giving it. It is a JSON object; a list of them is `JSON[]`.
3. **`Anything`** when the pipe is generic over its input — it passes a value along or renders it whatever it is. It is not the place to put JSON.
4. **`Dynamic`** is not recommended for inputs until L-260927-bea35e rules on what its slot holds.

This is the one place where the two aims of the language meet: the developer keeps their JSON as it is, and the method still says what that JSON is.

## Rejected alternatives

- **Infer the natural concept** (`native.Text` for a string, `native.JSON` for an object). It is what the bottom-up path does for a string today, and it has no answer for a heterogeneous `Anything[]`, since one stuff has one concept. It also discards the declaration for a guess, which is exactly what the item objected to.
- **A real `AnythingContent` class.** Rejected under R6.
- **Accept an array at a single `Anything` slot as a `ListContent`.** A single slot holding a list is what D2 exists to prevent, and every controller reads multiplicity through `Stuff.is_list`, so the stuff would be plural wherever it went while its slot says single.
- **Keep the `DYNAMIC` arm and teach the bottom-up factory about `Anything`.** The factory has no declared concept and no multiplicity to consult. That is the reason the top-down shaper exists.
- **Treat `JSON` as a structured concept**, so a bare object is the content and must carry `json_obj`. It matches the contract to the letter, but it refuses a plain object, which is what every caller of a `JSON` slot sends and what the report sent.
- **Keep the envelope in `JSON`'s compact template, and read a bare `{"json_obj": {…}}` as the content.** This was R7's first draft: it spared the corpus and both mirrors a projection change, and the collision rule kept a caller who copied the content out of the envelope from being wrapped twice. But it left every template a developer or an agent reads teaching a Python field name inside an envelope, while the shaper preferred the plain object, and it made one object shape mean two things at one slot. Fixing the template removes the reason for the rule.
- **A new error class for the fallback's refusal.** It would add a wire `error_type` for a case `StructureValidationError` already describes, and consumers branch on `error_type`.
- **Suggest an envelope in the fallback's refusal.** R8's first draft did. The advice is generic, the caller rarely knows which concept to name, and at a `Dynamic` slot the obvious one loses data.
- **Read an envelope-shaped list item as a per-item envelope**, keeping its content. It would match what a Python caller's `StuffContent` item already does, but the item's concept would be dropped, since a list stuff carries one concept, and only `Anything[]` and `JSON[]` would read it while every other list kind refuses it. Per-item envelopes, if wanted, are a feature for every kind.
- **Carry the content class on the wire beside an `Anything` value** (a type tag), instead of R9's plain value. A tag is a shape the runtime invents for a concept the standard says has none, and a consumer would still need Pipelex's class vocabulary to read it.

## What deliberately does not change

- **The input-form descriptor** still states `Anything` as `unknown` and `JSON` as an object with a `json_obj` field: the descriptor describes the content form, and the compact projection is what unwraps it.
- **`Anything`'s compact template keeps its envelope**, in the engine's light template and in all three projections, so `InputKind.ANYTHING` joins the `DYNAMIC` arm of `_delighten_entry` in `pipelex/pipe_machinery/rendering/input_renderer.py` and `Anything` stays in `OUT_OF_MATRIX_NATIVES`. Its bare placeholder, `{}`, would read as "send an object", while the envelope names the concept that says any value goes. `JSON` is the one that changes (R7): its light template unwraps `json_obj`, and it leaves `OUT_OF_MATRIX_NATIVES` in `pipelex/cli/dev_cli/commands/projection_reference.py`, `mthds-js/src/protocol/inputs_template.ts` and `mthds-python/mthds/protocol/inputs_template.py` together, so the engine and the projections agree and no divergence class opens.
- **The comment on `OUT_OF_MATRIX_NATIVES` goes stale in those three places.** It justifies keeping the envelope by saying an input shaper "cannot build" these natives top-down, which after R1 is no longer true of `Anything`. It should say instead that these are the open natives whose compact form keeps the envelope, because a bare value there either has no reading every runtime shares or, for `Anything`, would misstate what the slot takes.
- **Codegen** still emits `z.unknown()` and `Any` for an `Anything` slot. With R4, that type is wider than the contract by the array and the null; it is a declared imprecision of a structureless concept, which is how codegen already treats all three of them. Its `JSON` type stays `{ json_obj: … }`, the content form, like `{ text: … }` for `Text`.
- **Prompt attachment** stays a static decision on the declared concept, so an image handed to an `Anything` slot through a typed envelope renders as text in a `PipeLLM` prompt and is not attached. This is the same give-up `Dynamic` has, recorded on L-260901-45becb.
- **`native.Dynamic`** keeps its bottom-up arm. Its own data-loss bug, found here, is filed separately (below).

## Behaviour changes a caller can see

- A bare string at an `Anything` slot now produces a `native.Anything` stuff holding a `TextContent`, not a `native.Text` stuff. The content, and therefore every rendering of it, is identical, but the working memory, the run output and the graph now report the concept the method declared. `tests/unit/pipelex/core/memory/input_shaper/test_scalar_arms.py` pins the old behaviour (`anything-str-bottom-up`) and changes with it. This goes in the changelog under *Changed*.
- Every other JSON value, the published template and every typed envelope start being accepted.
- At a `JSON` slot, a bare object and a list of objects start being accepted, and a bare string, which used to become a `native.Text` stuff in that slot, is now refused as a wrong kind. That refusal is the fix, not a regression, and it goes in the changelog under *Changed* because a caller could have been relying on it.
- The compact inputs template for a `JSON` slot is now the bare object, in the engine (`pipelex codegen inputs`, the API's template) and in both projections.
- An item of a bare `Anything[]` or `JSON[]` list that is shaped like an envelope is refused (R10).
- At the remaining fallback slots, the refusal that used to be an unclassified `StuffFactoryError` is now a `StructureValidationError`: `input`-domained, naming the input and its concept, with a user action naming the declaration to change. A consumer branching on `error_type` sees a new value on this path.
- Under R4, `PipeInputContract.json_schema` for an `Anything` slot gains the `not` clause, which the shared projection corpus captures, so the committed capture changes in `mthds-js` and `mthds-python` in the same regeneration that retires the two `EXPECTED_UNSHAPEABLE` entries.

## Adjacent findings, filed

- L-260927-bea35e (`pipelex`, bug): a `native.Dynamic` envelope silently drops its object content, because `DynamicContent` declares no fields and inherits `extra="ignore"`. Measured: `{"a": 1, "b": "x"}` shapes into `DynamicContent()`. It now also carries the list half of the report: a bare object or a list of objects at a `Dynamic` slot has no reading at all, which after R8 is a typed refusal rather than an accepted value.
- L-260927-afaf62 (`mthds`, spec): the runtime guide's pseudo-code admits only native concepts into `Anything`.
- L-260927-da1b09 (`pipelex`, bug) and L-260927-223013 (`mthds`, spec): R9, the plain-value wire form of an `Anything` stuff's content.
- L-260927-a8ec06 (`mthds`, decision): open question 4.
- L-260927-702c56 (`pipelex`, feature): a `.json` or `.jsonl` file reference read into a `JSON[]` slot, the way D11 reads a CSV into a structured list.

## Open questions

1. **R4** — narrow the published schema by D2 and D9 (recommended), or leave it permissive and document the two refusals.
2. **R7's collision rule.** *Decided with Louis, 2026-09-27:* there is none. Every bare object is read literally, and `JSON`'s compact template becomes the bare object, so no caller learns the wrapped form.
3. **The corpus pipe.** `scaffold_anything_slot` exists only to isolate a declared gap. The plan folds `anything_in` back into `scaffold_open_natives`, the original intent of L-260902-543ad0, which removes one pipe's files from both mirrors and one entry from `conformance`'s corpus census. Keeping the separate pipe is equally correct and changes fewer files; the fold is recommended because a pipe whose only justification is a closed gap would need a new one.
4. **Should `JSON` hold any JSON value, not only an object?** A question for the standard, filed as L-260927-a8ec06 with its options. The recommendation is to keep it an object: widening makes a single `JSON` slot the one position that holds an array, against D2. Nothing in this design blocks on the answer; it builds and documents "a JSON object".
