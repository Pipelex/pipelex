# Typing `mode="before"` validators (Pydantic v2) — a short brief

## The core fact

A `@model_validator(mode="before")` (and `@field_validator(..., mode="before")`) runs **before Pydantic has coerced or validated anything**. It receives the *raw* input as handed to the model. For a model that input is usually a `dict`, but it can be anything the caller passed: a `str`, an `int`, `None`, an already-constructed instance, or — crucially — a value being trial-validated as one arm of a `Union`.

So the input type is genuinely unconstrained. Pydantic's own type stubs annotate the before-validator value as `Any`.

## What's pythonic for the annotation

Two honest options, in order of preference:

1. **`Any` in, `Any` out.** Truthful about the contract (raw, pre-validation input), and decoupled from any particular caller. The validator's job is to *normalize toward the dict shape*, not to assert it.
2. **An explicit `dict[str, Any] | T` union** — only when the model deliberately participates in a known `T`-vs-other union and you want the two expected shapes documented at the signature. This reads as self-documenting but is *circumstantial*: the non-dict arm names a sibling type from one consumer's union, so it leaks that consumer into the model. Avoid widening it past what you actually branch on.

Anti-pattern: annotating the value as `dict[str, Any]` when the validator can in fact receive a non-dict. That's a comfortable lie — it makes `values.get(...)` typecheck while the code crashes at runtime on a `str`/`None`.

## The load-bearing rule: guard on shape, inside the validator

```python
@model_validator(mode="before")
@classmethod
def normalize(cls, data: Any) -> Any:
    if not isinstance(data, dict):
        return data                      # let a later arm / the model machinery handle it
    # ... dict-only logic here ...
    return data
```

The `isinstance` guard — not the annotation — is what makes the validator robust. A before-validator should never assume its input shape.

## Why this matters for unions (the real trap)

Pydantic converts only `ValueError` and `AssertionError` raised inside a validator into a `ValidationError`. **Any other exception** (`AttributeError`, `TypeError`, `KeyError`, …) propagates unchanged.

Inside `Union` validation, Pydantic tries members and catches each member's `ValidationError` to move on to the next. A *non-`ValidationError`* exception is not caught — it aborts the whole union. So an unguarded before-validator that does `data.get(...)` on a `str` raises `AttributeError`, which escapes the union instead of cleanly rejecting that arm. The symptom looks like "this valid input doesn't match the union," but the cause is a validator that wasn't shape-safe.

## Don't fix it by reordering the union

Putting the simpler type first (`str | Model` instead of `Model | str`) can make the symptom vanish — Pydantic's default *smart* mode prefers an exact-type match, so a `str` input may hit the `str` arm and never invoke the model's before-validator. But this is masking at the wrong layer:

- it only helps the one call site whose ordering you changed;
- it doesn't protect `Model.model_validate(<non-dict>)` called directly, or any other union the model appears in;
- it depends on union-resolution behavior (smart vs `left_to_right`) that's easy to perturb later.

Fix the validator (guard on shape); treat union ordering as a readability choice, not a correctness mechanism.

## Smart vs left-to-right, in one line

Default `union_mode="smart"` picks the best-matching member regardless of declaration order (exact type matches win); `union_mode="left_to_right"` tries members top-to-bottom and takes the first that validates. Neither rescues a before-validator that raises a non-`ValidationError` on the arm it *does* try.

## Takeaways

- A before-validator receives `Any`; type it `Any` (or a deliberately-narrow union you actually branch on) — never a shape you merely hope for.
- Guard with `isinstance(...)` and return non-matching input untouched.
- Raise `ValueError`/`AssertionError` for real validation failures so Pydantic wraps them; let unexpected types fall through rather than crash.
- Robustness belongs on the model's validator, not on the order of a consumer's `Union`.
