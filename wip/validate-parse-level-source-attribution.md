# Deferred: thread `mthds_source` through parse-level validate failures

Code-review follow-up (greptile P1) on pipelex PR #992 (`feature/Tweaks-for-validation-api`). **Deferred** — recorded here for scoping rather than fixed in this PR, because it is a non-trivial runtime parse-path change, not a clear/small win.

## The gap

In `pipelex/pipeline/validate_bundle.py` (~line 286–291), the multi-file load builds blueprints per content with the source threaded in:

```python
content_sources = list(mthds_sources) if mthds_sources is not None else [None] * len(mthds_contents)
loaded_blueprints = [
    PipelexInterpreter.make_pipelex_bundle_blueprint(mthds_content=content, mthds_source=source)
    for content, source in zip(mthds_contents, content_sources, strict=True)
]
```

When one content has **malformed TOML**, `make_pipelex_bundle_blueprint()` raises *before* it seeds `mthds_source` into the blueprint data. The exception propagates out of the comprehension to the enclosing `_translate_to_validate_bundle_error(category="pipe")` context manager, which (with the structured-info GATE) yields a last-resort `blueprint_validation` residual **with no `source`**. So `validate_bundle(mthds_contents=[good, bad], mthds_sources=["a.mthds","bad.mthds"])` returns a structured error that cannot be attributed to `bad.mthds`.

## Why it matters

The vscode cross-file diagnostics path routes each `validation_errors[].source` to the owning editor file. A source-less parse error is unroutable (it also has no `pipe_code`/`concept_code` to fall back on), so a syntax error in a multi-file API request lands nowhere useful in the editor. (The PR #50 path-boundary fix in `crossFileDiagnostics.ts` only helps once a `source` exists.)

## Why it's deferred (not a quick patch)

- It needs the comprehension restructured into a per-item loop with a `try`/`except` around `make_pipelex_bundle_blueprint`, catching the **specific** interpreter parse exception (must be identified — no speculative `except`), so the current `source` can be attached.
- The residual category is currently `pipe` for this block (the `with _translate_to_validate_bundle_error(category="pipe")` scope); a parse-level failure is arguably `blueprint_validation`. Fixing attribution may also mean correcting the category — a second judgment call.
- The source must be plumbed into the residual item built by `build_validation_error_items` (`pipeline/validation_errors.py`) — i.e. convert the per-content parse failure into a `blueprint_validation` item carrying that source, rather than the generic translated residual.
- All of this sits on top of the Phase-2 + GATE logic; it carries regression risk against the just-landed structured-info invariant and deserves its own focused change + tests.

## Suggested shape (when picked up)

Loop per (content, source); on the specific parse exception, raise/emit a `blueprint_validation` `ValidationErrorItem` with `source=<this source>` and the parse message, so the GATE residual is no longer source-less. Add a unit test: two contents, the second malformed, assert the returned `validation_errors[]` has one item whose `source` is the second source. Then the conformance HTTP arm can assert parse-level source attribution on the real wire.
