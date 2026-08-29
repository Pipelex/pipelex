# Import the standard's wire models for the input-form descriptor and the pipe I/O contracts

This is the `pipelex` half of item 3.1 of the workspace input-form program (`../../../wip/input-form/plan.md` at the workspace root, ledger item `L-260826-db8dd5`). The program's decision D-1 gives the wire types of the input-form descriptor and of `pipe_io_contracts` to the standard's clients — `mthds/protocol` in TypeScript, `mthds.protocol` in Python — and D-3 says the engines import those models for what they emit rather than restating them. This document records what that meant here, and the calls taken along the way.

## What moved

`pipelex/pipeline/pipe_io_contracts.py` and `pipelex/pipeline/input_form.py` used to declare the wire shapes themselves. They no longer do: both modules now import the models from `mthds.protocol.pipe_io_contracts` and `mthds.protocol.input_form`, re-export them for the callers that already read them from here, and keep only what is genuinely this engine's — the builders, the deriver, and the exception conversion. The `mthds` floor moves to the release that carries those modules.

The wire is unchanged. Every field name, every value and every absent-versus-null rule is the one the engine already emitted; the derivation is the same derivation. What changed is which package declares the shape.

## The three shape differences the import forced

The standard's models are not a transcription of what this engine declared, so importing them was not a delete-and-import. Three differences did real work.

**The descriptor is a discriminated union, not one model with optional per-kind slots.** The standard declares `TextField`, `ProseField`, `DateField`, `NumberField`, `BooleanField`, `EnumField`, `DocumentField`, `ImageField`, `ObjectField`, `ListField` and `UnknownField`, each closed, with `InputFormField` the union discriminated on `kind`. That is strictly better than what was here — a `text` node can no longer carry `choices`, and a kind's required slots are simply required fields — but it means a node's kind is now its class. Two consequences ran through the deriver: constructing a node picks a class instead of passing a `kind=`, and the place that used to flip an existing node's kind by `model_copy(update={"kind": ...})` now rebuilds the node as the target class. That place is the intent-hint stamp, and the rebuild it needs is narrower than it first looks: `prose` and `label` are the only intent words that feed the kind, and both apply to text-valued sites alone, so the flip is always `text` ⟷ `prose` — two models sharing a base and therefore sharing every slot. `_recast_text_kind` is that rebuild, and it carries the shared text constraints across unchanged. It also states rather than asserts the invariant: a node that somehow reached it without being text-valued degrades to a plain hint stamp instead of raising.

**`FieldKind.is_list` and `is_object` are gone, and are not missed.** They existed to ask a flat model which arm it was on. With the union the question is `isinstance(node, ListField)` / `isinstance(node, ObjectField)`, which also narrows the type, so the callers that used to reach for `slot.fields` after an `is_object` check now do it with the type checker's agreement instead of against it.

**`datetime_flag` is `datetime`.** The old model spelled the slot `datetime_flag` in Python and renamed it in a serializer, to keep the attribute from shadowing the stdlib module name. The standard's `DateField` simply declares `datetime`, which is legal as a pydantic field and never shadows anything at module scope, so the serializer rename went with the declaration.

## `PresenceMarker` is now the standard's

The standard declares `PresenceMarker` in `mthds.protocol.pipe_io_contracts`, because the marker is part of the contract's wire vocabulary. This engine declared its own in `pipelex/core/pipes/variable_multiplicity.py`, with the same three members and the same meaning. Keeping both was not an option once the engine constructs the standard's models: the two enums are unrelated classes to a type checker, so every construction site would have needed a conversion, and the workspace would have kept two declarations of one wire enum — the thing D-1 exists to end.

So `variable_multiplicity.py` re-exports the standard's `PresenceMarker`. The three helpers it used to carry that are grammar rather than wire — parsing a marker symbol, rendering one, and asking whether a marker is the force assertion — became module-level functions in the same module (`presence_from_symbol`, `presence_symbol`, `is_force_presence`), so nothing about the `.mthds` suffix grammar left this repo. `is_optional` and `is_plain` come from the standard's enum, which declares both.

## How the unchanged wire was proved, not asserted

`mthds-python` commits one real payload pair captured from this engine's own derivation, byte-for-byte, as its Stage 2.3 parity fixture: `tests/fixtures/protocol/input_form.json` and `pipe_io_contracts.json`, produced by `pipelex-dev trace-input-semantics tests/data/input_semantics/hinted_bundle.mthds tests/data/input_semantics/probe_bundle.mthds` on `pipelex` 0.53.0 at checkout `bc97dad0b` — which is this change's merge base. Re-running that same command after the import and diffing the two hop-5 outputs against the committed fixture reports no difference on either artifact. The probe bundles exercise every construct the language accepts, so that is the whole emission, not a sample of it.

## The parse-time gates this turned on

The standard's models are closed shapes (`extra="forbid"`) and enforce cross-field invariants at the parse. Constructing them makes those invariants live gates on what this engine emits, which is the point: a divergence between the engine and the standard now fails loudly at derivation instead of silently on the wire. The gates that bear on the emission are the `item_count`/`multiplicity` pairing on both contract sides, the rule that a presence marker is never combined with multiplicity, the rule that a fixed count is at least two, the rule that a field never carries both `required: true` and a `default_value`, and the placement rule that `presence` and `gating` are stated on every top-level descriptor field and absent everywhere below it.

## Deliberately out of scope

The program's item 4.5 collects the engine-emission corrections the standard's pages made necessary — the fabricated `refines: ["native.Text"]` on description-only concepts and the `name` member on a list's `item` (`L-260826-0ed8dd`), `native.Date` emitted as `kind: "date"` and `native.Html` as `prose` where the standard's ordered table puts both on `object` (`L-260826-236839`), and `css_class` becoming optional on `native.Html` (`L-260826-3cea94`). None of them is a shape question, so none of them blocks this import, and none is folded in here. They are their own change.
