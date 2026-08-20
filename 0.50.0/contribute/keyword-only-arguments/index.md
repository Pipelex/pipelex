# Keyword-only arguments convention

This is the canonical convention for keyword-only function parameters across the `pipelex/` source tree (tests are out of scope). The goal is self-documenting call sites: when a function takes more than one meaningful argument, the caller must name them, so `do_thing(retries=3, timeout=30)` is forced over the unreadable `do_thing(3, 30)`. The convention is mechanically enforced by an AST guard (the `check-keyword-only` dev command, wired into both `make agent-check` and the `make check` family, and gated in CI). The `pipelex/` source tree is fully compliant, so the guard hard-blocks on **any** violation: new code must follow this convention or it fails the build. This document is the human-readable specification that guard implements.

## The rule

A function or method must place a bare `*` separator in its signature so that every parameter after the subject is keyword-only. The compliant shapes are:

```python
def f(*, opt1, opt2): ...            # fully keyword-only — always compliant, no registry entry needed
def f(subject, *, opt1, opt2): ...   # positional subject — compliant ONLY under a recorded subject grant
```

The first non-`self`/`cls` parameter — the subject — may stay positional-or-keyword **only when a subject grant for that def is recorded in `subject_grants.toml`** (see the next section). We deliberately do NOT use the positional-only `/` separator anywhere; a granted subject may be passed positionally or by keyword, at the caller's discretion.

A signature is a violation when any of these holds:

- **Missing bare `*`** — after dropping a leading `self`/`cls` and the subject, a positional-or-keyword parameter remains. Only the subject may ever be positional; everything after it must be named. So `def f(a, b)` and `def truncate(text, max_length=80)` are violations regardless of any grant.
- **Ungranted subject** — the def keeps a positional subject (`def render(node)`, `def f(spec, *, opt)`) but no grant for it exists in the registry.
- **Banned literal-typed subject** — the subject is annotated `bool`, `int`, or `float`, including their `Optional[X]` / `X | None` / `Union[X, None]` forms. This is a violation no matter what: a grant can never cover it, because call sites read as bare literals (`f(True)`, `retry(3)`) — exactly the opacity this convention exists to kill. `str` subjects remain grantable; they are the house style (`pipe_code`, `name`, `uri`, …). An unannotated subject is not provably literal and remains grantable.
- **Stale grant** — a registry entry whose def no longer exists, whose recorded `param` no longer matches the def's subject, or whose def no longer has a positional subject at all (demoted, renamed, moved, or newly carved out). Staleness is symmetric and hard-fails: a rename or file move forces a deliberate re-grant, not silent rot.

The registry carries one more rule that is not about any signature: its entries must stay in sorted key order (see [Staleness is symmetric](#staleness-is-symmetric)).

## Exception 1 — granted subject parameters

> **History note — this exception was narrowed, deliberately.** Exception 1 used to be a *generic* permission: any first non-`self`/`cls` parameter could stay positional, guard-approved, no questions asked. That judgment-shaped permission was systematically abused by coding agents, which left first arguments positional when they were not the subject or not obviously so — the check passed, so the prose was ignored. The permission is now an **explicitly granted, recorded exception**: judgment still exists, but it happens at grant time and in review of the registry diff, while CI stays 100% deterministic. Agents follow checks, not prose — so the check now carries the whole rule.

A def may keep its subject positional only under a **subject grant**: an entry in `subject_grants.toml` at the repo root, keyed by the def's stable identity (`<relative_path>::<qualified_name>`), recording the subject's parameter name and a one-sentence rationale:

```toml
version = 1

["pipelex/graph/render.py::render_node"]
param = "node"
rationale = "Verb–object: renders the node; single obvious operand."
```

The registry is machine-written and sorted by key, so diffs stay stable and merge conflicts resolve trivially — and that order is **checked**, not merely claimed here (`unsorted-grant`). An unsorted registry parses fine and grants exactly the same subjects, so a bulk rewrite that scrambles it — a package move, a sed over paths — would otherwise break the invariant silently. It is written **only** by the grant command; never edit it by hand except to delete a stale entry:

```bash
make subject-grant FUNC="pipelex/graph/render.py::render_node" RATIONALE="Verb–object: renders the node; single obvious operand."
# alias: make sgr — wraps: pipelex-dev subject-grant "<path>::<qualname>" --rationale "…"
```

The command validates the def (it must exist, be inspected by the guard, and have a positional non-literal-typed subject), records the `param` automatically, and rewrites the file sorted. It refuses literal-typed subjects, fully-keyword-only defs, carved-out defs, and empty rationales. Same-qualname defs (`@overload` stubs, conditional redefinitions) share one entry — the recorded `param` must match each of them, which forces overload stubs to align their subject name.

### What earns a grant — the rubric

A subject grant is warranted when EITHER:

- **Verb–object test:** the function name is a verb (phrase) and the param is its direct object — the call reads as a sentence (`render(node)`, `validate_bundle(bundle)`, `parse_concept_spec(spec_data)`) — AND it is the **single candidate** (if you hesitate between two params, neither is the subject) — AND typical call sites pass a **self-labelling expression**, never a bare literal (literal-typed subjects are banned outright anyway);
- OR the def must satisfy a **positional `Callable` protocol** (it is passed as a value to something that calls it positionally) and a grant keeps it compliant without reaching for the heavier `# kw-only: ignore`.

When in doubt → keyword-only. The grant is the exception tier; all-keyword is always compliant and often more readable. Rationales must be def-specific but may be terse for obvious keeps ("verb–object; single operand") — the value is that someone actually looked; copy-paste boilerplate across dozens of entries defeats the point.

The grant is a permission, not a requirement — making the subject keyword-only too is always allowed, needs no registry entry, and is frequently the better choice. The economics are intentional: `make fko` mechanically produces the all-keyword form, so the lazy path is the strict path; keeping a positional subject costs a deliberate command with an honest rationale, visible as a registry diff in every PR.

### Staleness is symmetric

The guard verifies the registry in both directions on every run: a positional subject without a grant fails, and a grant without a matching def fails (`dead-grant`), as does a grant whose recorded `param` no longer matches the def's subject (`grant-param-mismatch`). Renames, file moves, demotions to all-keyword, and newly added carve-outs (`@override`, framework decorators) all kill the grant — delete the entry or re-grant deliberately. A missing or malformed `subject_grants.toml` is an explicit check error, never treated as an empty registry (that would mass-flag every granted subject in the tree).

File order is checked alongside them (`unsorted-grant`). Order is read from the raw text, not from the parsed registry: TOML declares table order insignificant, so a `dict` is no evidence of what the file looks like. The text scan is cross-checked against the parsed keys, and a disagreement is an explicit check error rather than a quietly narrowed scan — an entry the scan cannot see would otherwise be exempt from the order rule without anyone knowing.

### Registry schema

A registry entry carries exactly two keys — `param` and `rationale`; anything else fails the check. When the registry was introduced, every pre-existing positional subject entered a transitional review grind (treated as new, not grandfathered); that transition is over — every grant now carries a genuine, def-specific review rationale. `pipelex-dev check-keyword-only --report` shows the full inventory and the per-package grant counts.

## Exception 2 — symmetric tuples (explicit allowlist only)

A small set of functions take a short, conventionally-ordered tuple of arguments where positional calling is the universally-understood form and naming would be pure noise: `clamp(value, low, high)`, `Point(x, y)`, `replace(text, old, new)`, `lerp(a, b, t)`, `set_env(key, value)`. These are exempt ENTIRELY — the whole function, including any trailing options — but ONLY via an explicit allowlist keyed by qualified name and file, curated in the guard's source (NOT in `subject_grants.toml` — the registry covers single subjects; the allowlist exempts whole functions, a different semantic). There is no pattern-based guessing: a function is symmetric-tuple-exempt if and only if it is listed in the allowlist. This keeps the carve-out auditable and prevents the exemption from quietly swallowing genuine subject-plus-options signatures, which are the main thing this convention wants to fix.

The curated allowlist is intentionally short. Each entry is a genuine ordered tuple under a well-known convention, not a subject followed by descriptive options.

- `pipelex.system.environment.set_env` — `set_env(key: str, value: str)`. Canonical key/value pair mirroring dict assignment; naming them would be pure noise.
- `pipelex.kit.single_file_agent_rules.unified_diff` — `unified_diff(before: str, after: str, path: str)`. `before`/`after` is the canonical ordered diff pair; `path` is the diff header. Reads as the universally-known diff convention.
- `pipelex.tools.misc.diff.diff_files` — `diff_files(path1, path2)`. Symmetric two-operand comparison; the `1`/`2` suffixes self-label ordering and there is no old/new semantics that keywords could clarify.
- `pipelex.tools.misc.diff.diff_dirs` — `diff_dirs(dir1, dir2)`. Same symmetric two-directory comparison; `dir1`/`dir2` is a self-labelling ordered pair.
- `pipelex.tools.typing.class_utils.are_classes_equivalent` — `are_classes_equivalent(class_1, class_2)`. Symmetric structural-equivalence check; order is irrelevant (equivalence is commutative) and the `1`/`2` suffixes self-label the operands. No trailing options.

The operating rule for two-operand functions — when only one of the operand-positional and the all-keyword form should win:

- **A clean symmetric/ordered pair with NO trailing options** may go on the allowlist and stay fully positional (the entries above). Order is either irrelevant (`are_classes_equivalent`) or universally understood (`diff_files`'s `1`/`2`).
- **A pair that also carries trailing options** is reshaped to fully keyword-only instead — the whole-function allowlist is all-or-nothing, so it cannot keep the pair positional while forcing the options keyword, and letting the options go positional is exactly the unreadable case this convention targets. Examples now keyword-only: `copy_file(*, source_path, target_path, overwrite=True)`, `mirror_dir(*, source_dir, target_dir, …)`, `sync_toml_values(*, source_path, target_path, dry_run=False)`, `has_diff_dirs(*, dir1, dir2, exclude_files=None, exclude_dirs=None)`, `is_multiplicity_compatible(*, source_multiplicity, target_multiplicity)`, the graph tracer's `add_edge(*, source_node_id, target_node_id, edge_kind, …)`.

This deliberately keeps the allowlist whole-function (no per-entry "leading positional count" machinery): the handful of pairs that would benefit from staying positional-with-keyword-options are rare enough that reshaping to all-keyword is the simpler, uniform answer.

Adding to the allowlist is a deliberate act: the entry must name a genuine ordered tuple under a recognized convention (key/value, x/y, min/max/clamp, before/after, src/dst, geometric coordinates, interpolation operands) with no trailing options, justified in the same conservative spirit as the entries above. When in doubt, leave it off and let the function be keyword-only — that is the safe default.

## Carve-outs (skipped entirely)

Carve-outs are different from exceptions: a carved-out def is never inspected at all, regardless of its parameter shape — it neither needs a subject grant nor can hold one alive. These are signatures the guard cannot or must not touch because some framework or the interpreter itself owns the calling convention.

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

Only `field_validator`, `model_validator`, and `model_serializer` are actually used in the source today; the v1 legacy names and `field_serializer` are included defensively so the guard stays correct if they are introduced later. Decorators may be call-form (`@field_validator("name", mode="before")`) or bare (`@model_serializer`); the guard handles both by unwrapping `ast.Call.func` when present and matching on the unqualified decorator name. The `parse_model_reference` helper referenced via `Annotated[..., BeforeValidator(parse_model_reference)]` is NOT a decorated def — it is a plain single-parameter module function (whose lone subject needs a grant like any other), and needs no carve-out.

### Framework entrypoints

A def is skipped when it is registered with a framework whose calling convention is not ours to dictate. Matching is on the decorator's attribute suffix (the receiver name varies — `app`, `graph_app`, `show_app`, `kit_app`, `build_app`, ...), and on the pytest decorators by their attribute/name:

- Typer/click commands and callbacks — any decorator that is an attribute access ending in `.command` or `.callback`. The guard scans the WHOLE decorator stack for a framework match (a framework decorator may sit above a custom one such as `@convert_pipelex_errors`), not just the innermost or outermost decorator.
- pytest fixtures — `fixture`, matched on the bare decorator name so both `@pytest.fixture` and bare `@fixture` (`from pytest import fixture`) are covered (the only src-side fixtures live in the shipped `pipelex/test_extras/shared_pytest_plugins.py` plugin module).
- Jinja2 filters/tests/globals — `pass_context`, `pass_environment`, `pass_eval_context`, matched on the bare decorator name (covers both `@pass_context` from `from jinja2 import pass_context` and the attributed `@jinja2.pass_context`). The Jinja2 engine invokes a filter POSITIONALLY from template syntax — `{{ value | tag("name") }}` calls `tag(context, value, "name")` — so the wrapped callable's arguments cannot be made keyword-only. This is the same framework-entrypoint category as Typer/pytest. A multi-argument filter without one of these decorators (rare) is covered by the `# kw-only: ignore` escape hatch; single-argument filters (`escape_script_tag(value)`) have an ordinary lone subject and take a grant like any other def.

FastAPI is intentionally absent: there are no route handlers in `pipelex/` source — the FastAPI server lives in the separate `pipelex-api/` repo.

Known coverage gap (documented, not silently ignored): some Typer commands are registered by call-style `app.command(name=...)(some_fn)` against functions defined in separate modules that carry NO decorator, so a decorator-keyed guard cannot see them via the framework carve-out. These target functions consistently type their parameters as `Annotated[T, typer.Argument(...)]` / `Annotated[T, typer.Option(...)]`. The guard treats a def as a framework entrypoint when any of its parameters carry `Argument`/`Option` metadata in their `Annotated[...]` annotation — matched on the trailing callee name, so both the qualified `typer.Option(...)` form and the bare `Option(...)` form (`from typer import Option`) are recognized — which closes the gap without resorting to a broad path-based exclusion of CLI modules.

### Base / Protocol / ABC overrides

A def decorated with `@override` (from `typing_extensions` / `typing`) is skipped. See the next section for why this single decorator is a complete and reliable signal in this codebase.

## Override handling — decision

DECISION: skip any def carrying an `@override` decorator. We do NOT introduce a dedicated `@kw_exempt` decorator for overrides, and we do NOT attempt base-aware (import-resolving / type-inferring) detection.

Rationale. An overriding method cannot freely re-shape its signature — it must stay compatible with the base/Protocol it implements — so the correct place to apply the keyword-only convention (and to record the subject grant, when the base keeps a positional subject) is the base definition, after which implementations inherit the contract and pyright's `reportIncompatibleMethodOverride` keeps them in line. Skipping `@override` defs is consistent with fixing the base. Crucially, `@override` is a reliable AND complete signal here: `pyproject.toml` sets `reportImplicitOverride = true`, so any method overriding a nominal base MUST carry `@override` or `make agent-check` already fails before the keyword-only guard runs — the marker cannot silently rot. Protocol implementations are structural and not forced by that setting, but house style applies `@override` to them consistently too; the residual risk is a hypothetical future Protocol implementor that forgets `@override`, which is already a style deviation the team avoids and is covered by the inline escape hatch below. A `@kw_exempt` decorator would duplicate semantics `@override` already carries and add a second redundant annotation to dozens of override sites for no gain. Base-aware detection would require import resolution a pure-AST guard cannot do reliably, and the codebase has already solved the problem for us via `reportImplicitOverride`. The guard matches `@override` structurally: a decorator that is an `ast.Name` with `id == "override"` or an `ast.Attribute` with `attr == "override"`, covering both `override` and `typing_extensions.override` without resolving imports.

## Inline escape hatch

A `# kw-only: ignore` comment on the `def` line (or the `async def` line) suppresses exactly one violation for that function — it short-circuits everything, including the subject-grant rules and the literal-subject ban. This is the documented fallback for the rare legitimate case the carve-outs and allowlist do not cover: chiefly a def some framework invokes positionally without a recognizable decorator (a `typer.Option(callback=...)` target like `version_callback(value: bool)`, an `__import__` hook, an SDK error callback), or a Protocol implementor that genuinely lacks `@override`. The escape hatch is the exception, not the mechanism: a reviewer seeing `# kw-only: ignore` should expect a short justification nearby. The marker is matched against the comment text on the def line; it suppresses the single def it sits on, not a whole class or module.

## Worked examples

A subject plus options — the canonical shape, legal only with a grant:

```python
# subject_grants.toml carries: ["pipelex/builder/build.py::build_pipe"] param = "spec" rationale = "…"
def build_pipe(spec, *, dry_run, retries, validate): ...   # build_pipe(my_spec, dry_run=True, retries=3, validate=False)
```

A single subject and nothing else — needs a grant too (strict-all scope; lone-subject defs are not implicitly exempt):

```python
def render(node): ...   # render(my_node) — granted: verb–object, single operand
```

All parameters named, including the first — always compliant, no registry entry, and often the most readable choice:

```python
def copy_payload(*, source, target): ...   # copy_payload(source=a, target=b)
```

Even a single defaulted option must be named — this is the common case the convention fixes, not an exception to it:

```python
# before: truncate(text, 120) — what does 120 mean?
def truncate(text, max_length=80): ...
# after: truncate(text, max_length=120) — with a grant for `text`, or fully keyword-only with none
def truncate(text, *, max_length=80): ...
```

A literal-typed subject — banned outright, no grant possible; make it keyword-only:

```python
# before: doctor_cmd(True) — reads as a bare literal
def doctor_cmd(fix: bool): ...
# after: doctor_cmd(fix=True)
def doctor_cmd(*, fix: bool): ...
```

A symmetric tuple on the allowlist — exempt entirely, stays positional:

```python
def set_env(key: str, value: str) -> None: ...   # set_env("PIPELEX_ENV", "prod")
```

A directional pair with a trailing option — neither operand is "the object", and a whole-function allowlist exemption would let the option go positional too, so the whole signature becomes keyword-only:

```python
# before — copy_file(src, dst, True): what does True mean?
def copy_file(source_path, target_path, overwrite=True): ...
# after — copy_file(source_path=src, target_path=dst, overwrite=False); every argument is named
def copy_file(*, source_path, target_path, overwrite=True): ...
```

A clean symmetric pair with no trailing options is the opposite case — it goes on the Exception 2 allowlist and stays fully positional (`are_classes_equivalent(class_1, class_2)`).

An override — skipped because of `@override`; fix (and grant) the base signature instead:

```python
@override
def _store(self, data, *, key, content_type): ...   # base StorageProviderAbstract._store defines the contract and holds any grant
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

The entire `pipelex/` source tree is compliant, so the guard hard-blocks on **any** violation — there is no baseline and no tolerated debt. Each violation kind names its own remedy in the check output:

| Kind | Meaning | Remedy |
|---|---|---|
| `missing-star` | a non-subject positional-or-keyword param remains | place the bare `*` (or `make fko`) |
| `ungranted-subject` | positional subject with no registry entry | `make fko` to go all-keyword, or `make subject-grant` |
| `literal-subject` | `bool`/`int`/`float` subject (incl. Optional/union-with-None) | make it keyword-only — grants are impossible |
| `grant-param-mismatch` | the grant's recorded `param` no longer matches the def | re-grant, or fix the registry |
| `dead-grant` | the grant matches no def with a positional subject | delete the entry (or re-grant after a rename/move) |
| `unsorted-grant` | the entry sits out of key order in the registry file | re-record any grant (it rewrites the file sorted), or move the entry back by hand |

The guard runs at several gates:

- A Claude Code `PostToolUse` hook (`.claude/hooks/check-keyword-only.sh`, wired in `.claude/settings.json`) — the tightest loop. After every `Edit`/`Write`/`MultiEdit` of a `pipelex/**/*.py` file it checks just that file and blocks with the offending signatures if it regressed, so an agent learns at edit time rather than at the end of the session. It runs the stdlib-only core by file path (no Typer/hub import), so it costs a few tens of milliseconds — including one `tomllib` read of the registry. The hook is check-only — it never rewrites a file mid-edit. It cannot see registry-level violations (dead grants and file order are whole-file concerns, invisible from one edited source file); the full check owns those.
- `make agent-check` — the fast everyday gate. It runs the **auto-fixing** variant (`fix-keyword-only`) early, right after `fix-unused-imports` and before `ruff format`, so a mechanically-fixable violation is corrected in place instead of failing the build. The fixer is **non-gating** — it reports the violations it can't mechanically fix but does not abort — so `format`, `lint`, `pyright`, and `mypy` all still run (you get keyword-only *and* type feedback in a single pass, and the tree is never left half-mutated and unformatted). The **read-only** `check-keyword-only` then runs **last** and is what actually blocks on any remaining violation. ⚠ Note the fixer's reach: an **ungranted subject def is a violation**, so `make agent-check` will silently keyword-only it — record the grant BEFORE running checks if you want the subject to stay positional.
- `make check` — the heavy aggregate gate. It runs the **check-only** `check-keyword-only` (no rewriting), so CI-equivalent runs stay read-only.
- CI — a dedicated lint job (`lint-keyword-only` in `.github/workflows/lint-check.yml`) gated by the required `Lint (all)` status check, so no non-compliant signature can merge. This is the hard guarantee; the hook and `make` gates are local conveniences layered on top. The registry diff in the PR is where grant judgment gets reviewed.

When you add or change a signature, place the bare `*` after the subject and grant the subject (or make everything keyword-only — no grant needed). If the type checker is blind to how a function is called (a framework or the interpreter invokes it positionally — a Jinja2 filter, an `__import__` hook, an aiohttp route handler, a PostHog `on_error` callback), the guard cannot detect that statically; the carve-outs above cover the known cases, and a genuinely justified one-off uses the `# kw-only: ignore` escape hatch. `make agent-test` is the safety net for these dynamic call surfaces — pyright/mypy will pass a wrongly-keywordized callback that the suite then catches at runtime.

## Auto-fix

`pipelex-dev check-keyword-only --fix` (exposed as `make fix-keyword-only` / `fko`, and run automatically inside `make agent-check`) rewrites every *mechanically-fixable* violation by inserting a bare `*` as far left as possible — immediately after `self`/`cls` (and after any `/`) — so **every** non-`self`/`cls` parameter becomes keyword-only, not just the ones after the subject: `def f(a, b)` becomes `def f(*, a, b)`, `def m(self, a, b)` becomes `def m(self, *, a, b)`, and an ungranted `def render(node)` becomes `def render(*, node)`. (The all-keyword form is always compliant and needs no grant — the fixer takes it.) `missing-star`, `ungranted-subject`, and `literal-subject` violations are all fixable this way; the registry-level kinds (`grant-param-mismatch`, `dead-grant`, `unsorted-grant`) are never rewritten — the fixer edits signatures, and the registry has exactly one writer, the grant command. The raw insert lands on the def's original line(s); the `make fix-keyword-only` / `fko` target runs `ruff format` right after the rewrite, so the standalone path leaves a `ruff format`-clean tree (inside `agent-check` the later `format` step would normalize it anyway). The rewrite is idempotent and is re-parsed before being written — a rewrite that would not parse is discarded and the violation reported instead.

A few shapes the guard flags cannot be fixed by a single bare-`*` insert, and are reported for a manual fix rather than rewritten:

- a `*args` is present — the parameters before it cannot be made keyword-only by a bare `*`, and a bare `*` cannot coexist with `*args`;
- a keyword-only section already exists (a bare `*` is already in the signature, with a positional parameter still ahead of it) — the existing `*` must be moved by hand, since a second one is a syntax error. This includes the common `def f(subject, *, opt)` shape when the subject is ungranted or literal-typed;
- two or more positional-only parameters (before a `/`, excluding a leading `self`/`cls`) remain — a bare `*` cannot precede the `/`, so they stay positional and cannot reach compliance mechanically. (A *single* positional-only subject still gets the `*` after the `/`, e.g. `def f(a, /, b, c)` → `def f(a, /, *, b, c)` — but the positional-only subject itself then still needs a grant or the `/` removed by hand.)

The `--fix` path is **non-gating**: it mutates and reports, but never exits non-zero on the violations it couldn't fix. The read-only `check-keyword-only` (no flag) owns the gating — it runs last in `agent-check` and is the variant `make check` / CI use. So `make fko` fixes what it can and prints the rest without failing your shell; run `make check-keyword-only` (alias `cko`) when you want the pass/fail gate. This split is deliberate: a tree-mutating step shouldn't also be the hard gate, or an abort could leave files rewritten-but-unformatted and mask the type-check phase.

Auto-fix is not a substitute for review: the guard is blind to framework-positional callers (see the safety-net note above), so a signature it "fixes" might be one some framework invokes positionally. And a fixed `ungranted-subject` def might have *deserved* its positional subject — if so, revert the def and record the grant instead. `make agent-test` remains the safety net — verify after a bulk auto-fix.

Run the guard directly to see the full picture:

```bash
make check-keyword-only            # alias: make cko — one line on pass, the per-kind violation list on fail
make fix-keyword-only              # alias: make fko — auto-insert the bare `*`; reports any manual-fix cases
make subject-grant FUNC="pipelex/….py::qualname" RATIONALE="…"   # alias: make sgr — record a subject grant
.venv/bin/pipelex-dev check-keyword-only --report   # full inventory by package + per-package grant counts
.venv/bin/pipelex-dev check-keyword-only --fix      # auto-fix (what `make fko` runs)

# Lean single-file check (what the PostToolUse hook runs): stdlib only, invoked by file path so it
# skips the pipelex package import chain. Prints violations to stderr and exits 2, else exits 0.
.venv/bin/python pipelex/cli/dev_cli/commands/keyword_only_guard.py pipelex/some/edited_file.py
```
