# Latent bug — `(ValueError, PipelexError)` exceptions never set `.message`, so `to_error_report()` raises

**Status:** flagged, **deferred** (pre-existing; out of scope for the Phase 5 Step 0b config relocation, which is behavior-neutral). Surfaced while verifying the C6 relocation of `TemporalConfigError` / `WorkerTaskQueueUnknownError` into core.

## The mechanism

`ValueError.__dict__` contains `__init__` (the C-level `BaseException` slot wrapper). So for a class declared `class X(ValueError, PipelexError)`, the MRO is `[X, …, ValueError, PipelexError, Exception, …]` and attribute lookup for `__init__` resolves to **`ValueError.__init__`** — *before* `PipelexError.__init__`. `PipelexError.__init__` is the only one that sets `self.message = message`; `ValueError.__init__` (i.e. `BaseException.__init__`) sets only `self.args`. Result: instances have **no `.message` attribute**.

`PipelexError.to_error_report()` reads `self.message`, so calling it on one of these instances raises `AttributeError: '…' object has no attribute 'message'` — masking the real error if it ever reaches an error-report rendering path (CLI JSON/agent output, HTTP problem-document).

Verified empirically (str()/args are fine; only `.message` and `to_error_report()` are affected):

```
WorkerTaskQueueUnknownError('boom')  ->  .message? False   str()='boom'  args=('boom',)
  to_error_report()  ->  AttributeError 'object has no attribute message'
ConfigModelError('x')                ->  .message? False   (identical, unchanged class)
```

## Affected classes (whole tree, today)

Every `class … (ValueError, <PipelexError-subclass>)`:

- `pipelex/system/configuration/exceptions.py` — `TemporalConfigError(ValueError, PipelexError)` and its subclass `WorkerTaskQueueUnknownError` (relocated here in Step 0b; the bug is **identical** to the pre-relocation `TemporalConfigError(ValueError, TemporalFlowError)` — `ValueError.__init__` won there too).
- `pipelex/system/exceptions.py` — `ConfigModelError(ValueError, FatalError)` (untouched by Step 0b).
- The temporal-side config subclasses `WorkerScopeConfigError` / `WorkerProfileConfigError` / `SearchAttributeRegistrationError` inherit from `TemporalConfigError` but **do not** re-add `ValueError` in their own bases, so they inherit the same broken `__init__` resolution transitively.

> Note: `ConfigValidationError(FatalError)` and other `(FatalError)`/`(PipelexError)`-only errors are **fine** — their MRO has the message-setting `__init__` first. Only the `ValueError`-first mixins are affected.

## Why it was deferred from Step 0b

Step 0b (codex C6) is a **behavior-neutral relocation** — move the Temporal config *schema* + its two exceptions to core so `pipelex/temporal/` can be externalized. Preserving the exact `(ValueError, PipelexError)` ordering keeps it byte-equivalent to the pre-move class. Fixing the `.message` gap **changes behavior** (instances gain `.message`; `to_error_report()` starts working) and spans the unrelated, unchanged `ConfigModelError` — so it belongs in its own deliberate change, not smuggled into a relocation commit.

## Proposed fix (separate change)

The `ValueError` mixin exists so Pydantic validators that `raise TemporalConfigError(msg)` are converted into a `ValidationError` (Pydantic catches `ValueError`/`TypeError`). `isinstance(x, ValueError)` is unaffected by base **order**, so the minimal correct fix is to **reorder the bases** so the message-setting `__init__` wins:

```python
class TemporalConfigError(PipelexError, ValueError): ...   # MRO: …, PipelexError, ValueError → PipelexError.__init__ sets .message
```

- Still `isinstance(_, ValueError)` → Pydantic still wraps validator raises; `str()`/`.args` unchanged.
- Now `.message` is set and `to_error_report()` works.

Apply uniformly to **every** `(ValueError, <PipelexError-subclass>)` class (sweep: `grep -rn 'class .*(ValueError,' pipelex/`). Add a regression test asserting both `.message == msg` and a successful `to_error_report()` for a representative class, plus a guard test that no `PipelexError` subclass lists `ValueError` *before* a message-setting base. First confirm whether any production path actually calls `to_error_report()` on these (worker-CLI / config-load error rendering) to set the priority — the str()-only paths are unaffected today.
