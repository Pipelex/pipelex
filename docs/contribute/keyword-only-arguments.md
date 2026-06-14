# Keyword-only arguments convention

This is the canonical convention for keyword-only function parameters across the `pipelex/` source tree (tests are out of scope). The goal is self-documenting call sites: when a function takes more than one meaningful argument, the caller must name them, so `do_thing(retries=3, timeout=30)` is forced over the unreadable `do_thing(3, 30)`. The convention is mechanically enforced by an AST guard (the `check-keyword-only` dev command, wired into both `make agent-check` and the `make check` family, and gated in CI). The `pipelex/` source tree is fully compliant, so the guard hard-blocks on **any** violation: new code must follow this convention or it fails the build. This document is the human-readable specification that guard implements.

## The rule

A function or method must place a bare `*` separator in its signature so that every parameter after the subject is keyword-only. The compliant shape is:

```python
def f(subject, *, opt1, opt2): ...
```

The first non-`self`/`cls` parameter — the subject — stays positional-or-keyword. We deliberately do NOT use the positional-only `/` separator anywhere; the subject is allowed to be passed positionally or by keyword, at the caller's discretion.

A signature is a violation when, after dropping a leading `self`/`cls` and the single allowed subject parameter, any positional-or-keyword parameter that is not already keyword-only remains. In other words, a function needs the bare `*` as soon as it would otherwise expose a *second* bare positional argument to callers: only the subject may be passed positionally, and everything after it must be named. Making the subject keyword-only too is always allowed — see Exception 1.

## The two exceptions

These two exceptions are part of the rule itself — they describe signatures that are compliant without a bare `*`.

### Exception 1 — the subject parameter

The first parameter after `self`/`cls` — the subject — *may* stay positional-or-keyword. This is a permission, not a requirement, and it exists for the same reason Swift lets you drop the first argument label with `_`: when the function name already designates what it acts on, naming the subject at the call site adds nothing (`render(node)`, `parse_blueprint(bp)`). A function with only a subject is compliant, and so is `def f(subject, *, opt1, opt2)` where every parameter after the subject is keyword-only.

Making the subject keyword-only too is always allowed and is frequently the better choice — `def f(*, source, target)` is fully compliant and often more readable than leaning on a positional subject. The exception only *permits* a positional subject; it never forces one. What the rule forbids is a *second* positional parameter: as soon as a non-subject parameter would be passed positionally, the bare `*` is required. So `def f(a, b)` and `def truncate(text, max_length=80)` are violations (`def f(a, *, b)`, `def truncate(text, *, max_length=80)`), while `def render(node)` and `def f(*, a, b)` are both fine.

### Exception 2 — symmetric tuples (explicit allowlist only)

A small set of functions take a short, conventionally-ordered tuple of arguments where positional calling is the universally-understood form and naming would be pure noise: `clamp(value, low, high)`, `Point(x, y)`, `replace(text, old, new)`, `lerp(a, b, t)`, `set_env(key, value)`. These are exempt ENTIRELY — the whole function, including any trailing options — but ONLY via an explicit allowlist keyed by qualified name and file. There is no pattern-based guessing: a function is symmetric-tuple-exempt if and only if it is listed in the allowlist. This keeps the carve-out auditable and prevents the exemption from quietly swallowing genuine subject-plus-options signatures, which are the main thing this refactor wants to fix.

The curated allowlist is intentionally short. Each entry is a genuine ordered tuple under a well-known convention, not a subject followed by descriptive options.

- `pipelex.system.environment.set_env` — `set_env(key: str, value: str)`. Canonical key/value pair mirroring dict assignment; naming them would be pure noise.
- `pipelex.kit.single_file_agent_rules.unified_diff` — `unified_diff(before: str, after: str, path: str)`. `before`/`after` is the canonical ordered diff pair; `path` is the diff header. Reads as the universally-known diff convention.
- `pipelex.tools.misc.diff.diff_files` — `diff_files(path1, path2)`. Symmetric two-operand comparison; the `1`/`2` suffixes self-label ordering and there is no old/new semantics that keywords could clarify.
- `pipelex.tools.misc.diff.diff_dirs` — `diff_dirs(dir1, dir2)`. Same symmetric two-directory comparison; `dir1`/`dir2` is a self-labelling ordered pair.

Three further candidates surfaced in the survey were deliberately left OFF the allowlist:

- `has_diff_dirs(dir1, dir2, exclude_files=None, exclude_dirs=None)`
- `copy_file(source_path, target_path, overwrite=True)`
- `sync_toml_values(source_path, target_path, dry_run=False)`

Each has a genuine ordered leading pair (`dir1`/`dir2`, `source`/`target`) but also carries trailing options. A whole-function allowlist exemption would let those options be passed positionally too — exactly the unreadable case the refactor targets — so they stay off the allowlist and are flagged as violations, to be resolved during their package's burn-down.

Open question for burn-down (the strict rule forces this): the allowlist is currently whole-function, so it cannot express "the leading directional pair may be positional, but the trailing options must be keyword". Under the strict rule, `copy_file(source_path, target_path, *, overwrite=True)` is itself still a violation, because `target_path` is a second positional. Two ways to resolve, decided per-function when its package is migrated:

- Reshape to a positional subject plus keyword-only rest: `copy_file(source_path, *, target_path, overwrite=True)`. Simple and fully compliant, at the cost of splitting the `src`/`dst` pair at the call site.
- Extend the allowlist to carry a per-entry *leading positional count* (e.g. `copy_file: 2`), so the genuine pair stays positional while the bare `*` still forces the options keyword. More faithful to directional-pair readability; a small guard enhancement.

Adding to the allowlist is a deliberate act: the entry must name a genuine ordered tuple under a recognized convention (key/value, x/y, min/max/clamp, before/after, src/dst, geometric coordinates, interpolation operands), justified in the same conservative spirit as the entries above. When in doubt, leave it off and let the function be keyword-only — that is the safe default.

## Carve-outs (skipped entirely)

Carve-outs are different from exceptions: a carved-out def is never inspected at all, regardless of its parameter shape. These are signatures the guard cannot or must not touch because some framework or the interpreter itself owns the calling convention.

### Dunder and operator methods

Any method whose name matches `^__[A-Za-z0-9_]+__$` (a leading and trailing double underscore around a real identifier body) is skipped. The interpreter and the data-model protocols invoke these positionally — `__init__`, `__eq__`, `__call__`, `__getitem__`, `__format__`, `__contains__`, `__enter__`, `__exit__`, and so on — and never by keyword, so forcing keyword-only would be both wrong and impossible to satisfy. The match is on the method NAME node only (not the source line), is a full-match (anchored), and requires a non-empty body between the underscore pairs so the degenerate `____` cannot match. This deliberately does NOT carve out name-mangled half-dunders (`__private` with no trailing `__`): those are ordinary methods we call ourselves, and they remain subject to the rule.

### Pydantic validators and serializers

A def decorated with any of these pydantic decorator names is skipped, because pydantic invokes the wrapped callable with a fixed positional protocol (`value`, `info`, `handler`, ...) that we do not control:

- `field_validator`
- `model_validator`
- `field_serializer`
- `model_serializer`
- `validator` (pydantic v1 legacy)
- `root_validator` (pydantic v1 legacy)

Only `field_validator`, `model_validator`, and `model_serializer` are actually used in the source today; the v1 legacy names and `field_serializer` are included defensively so the guard stays correct if they are introduced later. Decorators may be call-form (`@field_validator("name", mode="before")`) or bare (`@model_serializer`); the guard handles both by unwrapping `ast.Call.func` when present and matching on the unqualified decorator name. The `parse_model_reference` helper referenced via `Annotated[..., BeforeValidator(parse_model_reference)]` is NOT a decorated def — it is a plain single-parameter module function, already compliant under the single-parameter rule, and needs no carve-out.

### Framework entrypoints

A def is skipped when it is registered with a framework whose calling convention is not ours to dictate. Matching is on the decorator's attribute suffix (the receiver name varies — `app`, `graph_app`, `show_app`, `kit_app`, `build_app`, ...), and on the Temporal and pytest decorators by their attribute/name:

- Typer/click commands and callbacks — any decorator that is an attribute access ending in `.command` or `.callback`.
- Temporal handlers — `activity.defn`, `workflow.run`, and defensively `workflow.signal`, `workflow.query`, `workflow.update` (none of the latter three are used yet, but they are part of the worker entrypoint surface). Note `workflow.defn` decorates classes, not functions, so it is irrelevant. The custom `@convert_pipelex_errors` decorator is stacked directly below `@activity.defn` and is NOT a framework decorator — the guard must scan the WHOLE decorator stack for a framework match, not just the innermost or outermost decorator.
- pytest fixtures — `fixture`, matched on the bare decorator name so both `@pytest.fixture` and bare `@fixture` (`from pytest import fixture`) are covered (the only src-side fixtures live in the shipped `pipelex/test_extras/shared_pytest_plugins.py` plugin module).
- Jinja2 filters/tests/globals — `pass_context`, `pass_environment`, `pass_eval_context`, matched on the bare decorator name (covers both `@pass_context` from `from jinja2 import pass_context` and the attributed `@jinja2.pass_context`). The Jinja2 engine invokes a filter POSITIONALLY from template syntax — `{{ value | tag("name") }}` calls `tag(context, value, "name")` — so the wrapped callable's arguments cannot be made keyword-only. This is the same framework-entrypoint category as Typer/Temporal/pytest. A multi-argument filter without one of these decorators (rare) is covered by the `# kw-only: ignore` escape hatch; single-argument filters (`escape_script_tag(value)`) are compliant under the single-parameter rule and need nothing.

FastAPI is intentionally absent: there are no route handlers in `pipelex/` source — the FastAPI server lives in the separate `pipelex-api/` repo.

Known coverage gap (documented, not silently ignored): some Typer commands are registered by call-style `app.command(name=...)(some_fn)` against functions defined in separate modules that carry NO decorator, so a decorator-keyed guard cannot see them via the framework carve-out. These target functions consistently type their parameters as `Annotated[T, typer.Argument(...)]` / `Annotated[T, typer.Option(...)]`. The guard treats a def as a framework entrypoint when any of its parameters carry `Argument`/`Option` metadata in their `Annotated[...]` annotation — matched on the trailing callee name, so both the qualified `typer.Option(...)` form and the bare `Option(...)` form (`from typer import Option`) are recognized — which closes the gap without resorting to a broad path-based exclusion of CLI modules.

### Base / Protocol / ABC overrides

A def decorated with `@override` (from `typing_extensions` / `typing`) is skipped. See the next section for why this single decorator is a complete and reliable signal in this codebase.

## Override handling — decision

DECISION: skip any def carrying an `@override` decorator. We do NOT introduce a dedicated `@kw_exempt` decorator for overrides, and we do NOT attempt base-aware (import-resolving / type-inferring) detection.

Rationale. An overriding method cannot freely re-shape its signature — it must stay compatible with the base/Protocol it implements — so the correct place to apply the keyword-only convention is the base definition, after which implementations inherit the contract and pyright's `reportIncompatibleMethodOverride` keeps them in line. Skipping `@override` defs is consistent with fixing the base. Crucially, `@override` is a reliable AND complete signal here: `pyproject.toml` sets `reportImplicitOverride = true`, so any method overriding a nominal base MUST carry `@override` or `make agent-check` already fails before the keyword-only guard runs — the marker cannot silently rot. Protocol implementations are structural and not forced by that setting, but house style applies `@override` to them consistently too; the residual risk is a hypothetical future Protocol implementor that forgets `@override`, which is already a style deviation the team avoids and is covered by the inline escape hatch below. A `@kw_exempt` decorator would duplicate semantics `@override` already carries and add a second redundant annotation to dozens of override sites for no gain. Base-aware detection would require import resolution a pure-AST guard cannot do reliably, and the codebase has already solved the problem for us via `reportImplicitOverride`. The guard matches `@override` structurally: a decorator that is an `ast.Name` with `id == "override"` or an `ast.Attribute` with `attr == "override"`, covering both `override` and `typing_extensions.override` without resolving imports.

## Inline escape hatch

A `# kw-only: ignore` comment on the `def` line (or the `async def` line) suppresses exactly one violation for that function. This is the documented fallback for the rare legitimate case the carve-outs and allowlist do not cover — for example a Protocol implementor that genuinely lacks `@override`, or a one-off signature whose positional shape is justified and does not merit a permanent allowlist entry. The escape hatch is the exception, not the mechanism: the carve-outs and the `@override` skip are expected to handle the vast majority of legitimate non-compliant signatures, and a reviewer seeing `# kw-only: ignore` should expect a short justification nearby. The marker is matched against the comment text on the def line; it suppresses the single def it sits on, not a whole class or module.

## Worked examples

A subject plus options — the canonical thing this refactor fixes:

```python
# before — opaque at the call site: build_pipe(my_spec, True, 3, False)
def build_pipe(spec, dry_run, retries, validate): ...

# after — self-documenting: build_pipe(my_spec, dry_run=True, retries=3, validate=False)
def build_pipe(spec, *, dry_run, retries, validate): ...
```

A single subject and nothing else — compliant; the subject may be passed positionally:

```python
def render(node): ...   # render(my_node)
```

All parameters named, including the first — always compliant, and often the most readable choice:

```python
def copy_payload(*, source, target): ...   # copy_payload(source=a, target=b)
```

Even a single defaulted option must be named — this is the common case the refactor fixes, not an exception to it:

```python
# before: truncate(text, 120) — what does 120 mean?
def truncate(text, max_length=80): ...
# after: truncate(text, max_length=120)
def truncate(text, *, max_length=80): ...
```

A symmetric tuple on the allowlist — exempt entirely, stays positional:

```python
def set_env(key: str, value: str) -> None: ...   # set_env("PIPELEX_ENV", "prod")
```

A directional pair with a trailing option — under the strict rule only the subject may stay positional, so the second operand and the option both become keyword-only:

```python
# before — copy_file(src, dst, True): what does True mean?
def copy_file(source_path, target_path, overwrite=True): ...
# after — copy_file(src, target_path=dst, overwrite=False); only the subject stays positional
def copy_file(source_path, *, target_path, overwrite=True): ...
```

Keeping the `source_path`/`target_path` pair positional while still forcing `overwrite` keyword is not expressible today; it would need the per-entry leading-positional-count allowlist extension described in the Exception 2 open question for burn-down.

An override — skipped because of `@override`; fix the base signature instead:

```python
@override
def _store(self, data, *, key, content_type): ...   # base StorageProviderAbstract._store defines the kw-only contract
```

A dunder — skipped by name; the interpreter owns the calling convention:

```python
def __format__(self, format_spec: str) -> str: ...   # called positionally by format()/f-strings
```

A pydantic validator — skipped by decorator; pydantic owns the positional protocol:

```python
@field_validator("some_field", mode="before")
def normalize(cls, value, info): ...
```

## Enforcement

The entire `pipelex/` source tree is compliant, so the guard hard-blocks on **any** violation — there is no baseline and no tolerated debt. The guard runs in three places:

- `make agent-check` — the fast everyday gate, so a new violation surfaces in the tight edit loop.
- `make check` — the heavy aggregate gate.
- CI — a dedicated lint job (`lint-keyword-only` in `.github/workflows/lint-check.yml`) gated by the required `Lint (all)` status check, so no non-compliant signature can merge.

When you add or change a signature, place the bare `*` after the subject. If the type checker is blind to how a function is called (a framework or the interpreter invokes it positionally — a Jinja2 filter, an `__import__` hook, an aiohttp route handler, a PostHog `on_error` callback), the guard cannot detect that statically; the carve-outs above cover the known cases, and a genuinely justified one-off uses the `# kw-only: ignore` escape hatch. `make agent-test` is the safety net for these dynamic call surfaces — pyright/mypy will pass a wrongly-keywordized callback that the suite then catches at runtime.

Run the guard directly to see the full picture:

```bash
make check-keyword-only            # alias: make cko — one line on pass, the full violation list on fail
.venv/bin/pipelex-dev check-keyword-only --report   # full inventory grouped by package
```
