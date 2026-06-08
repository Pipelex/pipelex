# Refactor: `PipeSignature` is a blueprint-layer contract, not an executable pipe type

> **Status:** proposed, pre-merge. Raised by review of the additive-multi-file PR: *"I disagree that it's a new type of pipe. Pipe signatures are a substrate of the `PipeAbstract`. Each pipe has a pipe signature."* This plan implements the agreed reconciliation.

## The decision

Keep `PipeSignature(PipeAbstract)` — it stays a `PipeAbstract` subclass, because the dry-run engine dispatches over `PipeAbstract` and a signature must be dry-runnable (verify inputs, mock output). But **evict it from the executable-kind taxonomy**: remove `PipeSignature` from the `PipeType` and `PipeCategory` enums, and identify "is this a signature?" by class, not by an enum field.

`signature_for: PipeType | None` **stays as a field** for now (it is consumed by `../mthds-plugins` and we don't want to break that). Its two `reject_signature_for_pipe_signature` guard validators are **deleted** — see [the forced interaction](#the-signature_for-interaction) below.

This is **not** the "Option A" collapse (a `signature = true` flag on a real operator type, optional bodies on `PipeLLM`, etc.). That was explicitly rejected: a signature is a contract that stands on its own, **not** a pending/incomplete version of a concrete pipe.

## The diagnosis (why it ended up looking like a pipe type)

`PipeType` and `PipeCategory` each silently do **two jobs**:

1. A **parse-time allowlist** — "is this `type` string legal under `[pipe.X]`?" (`PipeBlueprint.validate_pipe_type`, `PipeAbstract.validate_pipe_type`, `PipeSpec.validate_pipe_type`, all checking `value in PipeType.value_list()`).
2. The **executable-kind / orchestration-role taxonomy** — `PipeType.category` → operator vs controller; `PipeCategory.is_controller`.

A signature legitimately belongs in job (1): `type = "PipeSignature"` is a real thing you write in a bundle. But the only way to clear that allowlist was to also become a `PipeType` member — which **forced** it to claim a `.category`, which dragged it into job (2) as a sibling of `PipeLLM`/`PipeSequence`. `PipeCategory.PIPE_SIGNATURE` (a peer of `PIPE_OPERATOR`/`PIPE_CONTROLLER`) is the visible scar. The fix separates the two jobs: the allowlist becomes "executable kinds ∪ the signature tag"; the taxonomy enums shrink back to executable kinds only.

## The principle

- **`PipeAbstract` = the substrate** (contract-bearing graph node: `inputs` / `output` / `description`, dry-runnable). A `PipeSignature` is that substrate with nothing added. It stays here. *(This is exactly the co-dev's "substrate of `PipeAbstract`".)*
- **`PipeType` / `PipeCategory` = the executable taxonomy** (how a pipe runs and whether it orchestrates). A signature does not run, so it is in **neither**.
- **Identity by class, not by enum field.** `is_signature` becomes a class fact (base returns `False`; `PipeSignature` / `PipeSignatureBlueprint` override to `True`), so it no longer reads `pipe_category`. Every existing `is_signature` call site keeps working unchanged — that property is the keystone.
- **The runtime `PipeSignature` is the dry-run shim of a blueprint-layer contract.** Fully determined by the contract; carries no body. Live-run always errors; dry-run mocks, and only under `--allow-signatures`.

## Scope decision: the spec layer stays put

`../mthds-plugins` authors against the **spec** layer (`PipeSignatureSpec`, including `signature_for`). To keep that external surface stable, the spec layer keeps its `type = "PipeSignature"` and `pipe_category = "PipeSignature"` string literals — they are display/authoring tags, they are **not** typed as `PipeCategory`, and `PipeSignatureSpec.to_blueprint()` does not propagate `pipe_category` into the blueprint anyway. The only required spec-layer edits are: widen `PipeSpec.validate_pipe_type` to admit the signature tag, and delete the now-broken `signature_for` guard. The taxonomy correction lands at the **blueprint + runtime** layers, where it belongs.

---

## Implementation steps

### Step 1 — Keystone: `is_signature` by class

`pipelex/core/pipes/pipe_abstract.py` — replace the enum-based property (currently `return PipeCategory(self.pipe_category) is PipeCategory.PIPE_SIGNATURE`, lines 71-73) with a base that returns `False`:

```python
@property
def is_signature(self) -> bool:
    return False
```

`pipelex/pipe_signature/pipe_signature.py` — add the override:

```python
@property
@override
def is_signature(self) -> bool:
    return True
```

`pipelex/core/pipes/pipe_blueprint.py` — same on `PipeBlueprint` (lines 107-109 → `return False`).
`pipelex/pipe_signature/pipe_signature_blueprint.py` — add the `is_signature → True` override.

**Step 1b (recommended, same principle, optional):** convert `PipeAbstract.is_controller` (lines 67-69) the same way — base `return False`, `PipeController` overrides `return True` — so `is_controller` also stops reading `pipe_category`. Without this, `is_controller` still works for a signature (it calls `PipeCategory.is_controller_by_str(None)`, which hits `except ValueError → False`), so 1b is cleanliness, not correctness. Do it unless we want the smallest possible diff.

### Step 2 — Shrink the enums

`pipelex/core/pipes/pipe_blueprint.py`:

- `PipeCategory`: delete `PIPE_SIGNATURE = "PipeSignature"` (line 16). In `is_controller` (the match), drop `PipeCategory.PIPE_SIGNATURE` from the `case PipeCategory.PIPE_OPERATOR | PipeCategory.PIPE_SIGNATURE:` arm → `case PipeCategory.PIPE_OPERATOR:`. Still exhaustive over `{OPERATOR, CONTROLLER}`.
- `PipeType`: delete `PIPE_SIGNATURE = "PipeSignature"` (line 54). In `.category`, delete the `case PipeType.PIPE_SIGNATURE: return PipeCategory.PIPE_SIGNATURE` arm (lines 85-86). `.category` is now a **total** function over executable kinds — which is the tidiness win that makes eviction strictly better than keeping it with an `Optional` return.

### Step 3 — Tolerate the signature in the shared validators

The signature's `type` ("PipeSignature") is no longer in `PipeType.value_list()`, and its `pipe_category` becomes `None` (Step 5). The base validators on **both** `PipeBlueprint` and `PipeAbstract` need three small allowances:

- `validate_pipe_type` (field, after): admit the signature tag.

  ```python
  if value not in PipeType.value_list() and value != PipeSignatureBlueprint type tag "PipeSignature":
      raise ...
  ```

  Express the allowlist honestly — define a module-level `PIPE_SIGNATURE_TYPE_TAG = "PipeSignature"` in `pipe_blueprint.py` and check `value not in PipeType.value_list() and value != PIPE_SIGNATURE_TYPE_TAG`. (Avoid importing `PipeSignatureBlueprint` into the base module — that's a cycle; a bare string constant is the right tool.)

- `validate_pipe_category` (field, after): admit `None`.

  ```python
  if value is not None and value not in PipeCategory.value_list():
      raise ...
  ```

  Only signatures carry `None` (executable subclasses pin `Literal["PipeOperator"|"PipeController"]`), so this is safe.

- `validate_pipe_category_based_on_type` (model, after): early-return for signatures, before the `PipeType(self.type)` coercion that would now raise.

  ```python
  def validate_pipe_category_based_on_type(self) -> Self:
      if self.is_signature:
          return self
      ...
  ```

  `is_signature` is class-based after Step 1, so this is reliable at model-validation time.

### Step 4 — Factory: branch around the `PipeType` coercion

`pipelex/core/pipes/pipe_factory.py` (lines 105-106) currently does `pipe_type = PipeType(blueprint.type)` then `pipe_category = pipe_type.category` — both raise for a signature. Branch on `is_signature` and resolve the factory by name from the string (no `PipeSignatureFactory` import → no cycle; the class-registry lookup already in place resolves it):

```python
if blueprint.is_signature:
    pipe_category = None
    factory_class_name = f"{blueprint.type}Factory"   # "PipeSignatureFactory"
else:
    pipe_type = PipeType(blueprint.type)
    pipe_category = pipe_type.category
    factory_class_name = f"{pipe_type.value}Factory"
```

The existing registry lookup + `pipe_factory.make(pipe_category=pipe_category, ...)` call (lines 110-131) stays. `PipeSignatureFactory.make` already accepts `pipe_category: Any`; it ignores it and builds the shim.

### Step 5 — Signature runtime + blueprint: `pipe_category` → `None`

- `pipelex/pipe_signature/pipe_signature.py` (line 28): `pipe_category: Literal["PipeSignature"] = "PipeSignature"` → `pipe_category: None = None`. (`type` stays `Literal["PipeSignature"]` — it's the blueprint tag, still the discriminator string.)
- `pipelex/pipe_signature/pipe_signature_blueprint.py` (line 18): → `pipe_category: None = Field(default=None, exclude=True)`. **Keep `exclude=True`** — overriding the field type drops the base's `Field(exclude=True)` unless re-specified, and we still don't want `pipe_category` serialized into round-tripped `.mthds`.

The discriminated union (`PipeBlueprintUnion`) discriminates on `type`, not `pipe_category`, so `None` here is invisible to parsing.

### Step 6 — `output_renderer` guard

`pipelex/core/pipes/output/output_renderer.py`: line 32 `PipeType(the_pipe.type)` raises for a signature, and the match arm (lines 99-110) lists `PipeType.PIPE_SIGNATURE`. Add an early return and drop the arm:

```python
if the_pipe.is_signature:
    return []
pipe_type = PipeType(the_pipe.type)
...
case (PipeType.PIPE_FUNC | ... | PipeType.PIPE_PARALLEL):   # PIPE_SIGNATURE removed
    return []
```

Still exhaustive over the shrunken `PipeType`.

### Step 7 — Delete the `signature_for` guards (keep the field) {#the-signature_for-interaction}

`pipelex/pipe_signature/pipe_signature_blueprint.py` (lines 24-30) and `pipelex/builder/pipe/pipe_signature_spec.py` (lines 53-59): **delete** both `reject_signature_for_pipe_signature` validators. They reference `PipeType.PIPE_SIGNATURE`, which no longer exists → they would raise `AttributeError` whenever a signature is parsed. Their intent (forbid `signature_for=PipeSignature`) is now enforced structurally: `signature_for: PipeType | None` can no longer coerce the string `"PipeSignature"`, so Pydantic rejects it with a clean validation error.

`signature_for` itself, `PipeSignatureFactory`'s `signature_for=blueprint.signature_for` pass-through (line 32), and `PipeSignatureSpec.to_blueprint`'s `signature_for=self.signature_for` (line 67) all **stay**. Soften the docstrings that say "cannot itself be `PipeSignature`" (`pipe_signature_spec.py` lines 42-43) since the enum now enforces it.

### Step 8 — Spec layer: widen `validate_pipe_type`

`pipelex/builder/pipe/pipe_spec.py` (lines 79-85): same widening as Step 3's `validate_pipe_type` — admit the signature tag so `PipeSignatureSpec` still validates. No other spec-layer change (see [scope decision](#scope-decision-the-spec-layer-stays-put)); `pipe_spec_map.py:27` (`"PipeSignature": PipeSignatureSpec`) is a string-keyed map and is unaffected.

---

## ⛳ Checkpoint — run the core gate before docs

After Steps 1-8 (all code), this is the risky core. Run and get green before touching prose:

- `make tb` — boot/config load (catches enum + Pydantic field breakage fast).
- `.venv/bin/pipelex-dev generate-mthds-schema` — regenerate `derived/mthds_schema.json` (the `PipeSignatureBlueprint` definition still exists in the union; `_PIPE_INTERNAL_FIELDS = {"pipe_category"}` still strips the field). Commit the regenerated schema.
- `make agent-check` — ruff / pyright / mypy / plxt.
- `make agent-test` — full suite. Expect edits in the signature/taxonomy unit tests that asserted `PipeCategory.PIPE_SIGNATURE` or `signature_for` rejection messages; update them to the new model.

### Step 9 — Docs / CHANGELOG / TODOS reframe

- `docs/building-methods/pipes/signature-pipes.md` — stop framing it as "a new type of pipe." Frame: every pipe *has* a signature (its contract); a `PipeSignature` is the contract alone — a blueprint-layer declaration whose runtime form is a dry-run-only mock shim, deliberately outside the executable `PipeType`/`PipeCategory` taxonomy.
- `TODOS.md` change #1 ("Pipe signature ↔ concrete reconciliation") — reword from "replace pipe-type `PipeSignature` with pipe-type `PipeLLM`" to "**a contract fulfilled by an implementation**" (the reconciliation table is unchanged; `contracts_match` is unchanged).
- `CHANGELOG.md` `[Unreleased]` — note: `PipeSignature` moved out of the `PipeType`/`PipeCategory` taxonomy; `PipeCategory.PIPE_SIGNATURE` removed (breaking for anything matching on it); `signature_for` retained.

---

## A welcome side effect

The headline feature reads truer. `library_crate_factory._reconcile_pipe_collision` keys off `blueprint.is_signature` (lines 169-190) — after this it means **"a contract is fulfilled by an implementation,"** not "swap pipe-type `PipeSignature` for pipe-type `PipeLLM`." `contract_match.contracts_match()` is untouched.

## Out of scope / future

- **Eventually retire `signature_for`.** Kept now only for `../mthds-plugins`. It is an advisory implementor hint pointing at an *implementable* kind — it is **not** the signature's underlying type (a signature has no underlying type). Revisit once mthds-plugins no longer depends on it; likely fold any hint into `description` rather than a typed field.
- **`pipe_category` is itself redundant** — it must equal `PipeType(type).category` for executable pipes and is now `None` for signatures. It could later be derived rather than stored. Not in this change.
- **`is_controller` class-conversion** (Step 1b) can be deferred if minimizing diff.

## Touch-point index

| File | What |
| --- | --- |
| `pipelex/core/pipes/pipe_blueprint.py` | shrink both enums; `PipeBlueprint.is_signature` → `False`; widen `validate_pipe_type` / `validate_pipe_category`; `validate_pipe_category_based_on_type` early-return; add `PIPE_SIGNATURE_TYPE_TAG` |
| `pipelex/core/pipes/pipe_abstract.py` | `is_signature` → `False` base; same validator widening; (1b) `is_controller` → `False` base |
| `pipelex/pipe_signature/pipe_signature.py` | `pipe_category: None = None`; `is_signature` override → `True` |
| `pipelex/pipe_signature/pipe_signature_blueprint.py` | `pipe_category: None = Field(default=None, exclude=True)`; `is_signature` override → `True`; delete guard validator |
| `pipelex/pipe_signature/pipe_signature_factory.py` | no change (still passes `signature_for`) |
| `pipelex/pipe_controllers/pipe_controller.py` | (1b only) `is_controller` override → `True` |
| `pipelex/core/pipes/pipe_factory.py` | branch on `is_signature` around the `PipeType` coercion |
| `pipelex/core/pipes/output/output_renderer.py` | early `is_signature` return; drop `PIPE_SIGNATURE` match arm |
| `pipelex/builder/pipe/pipe_spec.py` | widen `validate_pipe_type` |
| `pipelex/builder/pipe/pipe_signature_spec.py` | delete guard validator; soften docstring; keep tags + `signature_for` |
| `derived/mthds_schema.json` | regenerate |
| tests + docs + CHANGELOG | per Steps 8-9 |

`registry_models.py` (`PIPE_SIGNATURES` / `PIPE_SIGNATURES_FACTORY` ClassVars) **stays** — keeping signatures as their own registry group reinforces "not an operator/controller."

## Checklist

- [ ] Step 1 — `is_signature` class-based (abstract + blueprint + overrides); (1b) `is_controller`
- [ ] Step 2 — `PIPE_SIGNATURE` out of `PipeType` + `PipeCategory` (+ match arms)
- [ ] Step 3 — base validators tolerate the signature tag + `None` category + early-return
- [ ] Step 4 — factory branch
- [ ] Step 5 — signature `pipe_category` → `None` (keep blueprint `exclude=True`)
- [ ] Step 6 — `output_renderer` guard
- [ ] Step 7 — delete `signature_for` guards, keep the field
- [ ] Step 8 — spec `validate_pipe_type` widened
- [ ] ⛳ `make tb` + schema regen + `make agent-check` + `make agent-test` green
- [ ] Step 9 — docs / CHANGELOG / TODOS reframed
