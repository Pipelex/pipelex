# Deferred: should the TypeScript emission gate enforce its own prettier pin?

Deferred from PR [#1184](https://github.com/Pipelex/pipelex/pull/1184) review round 1 (2026-09-02). Raised by cubic, running locally against `origin/dev` — it left no PR thread, so this note is its only record.

## The issue as reported

`Makefile:35` declares the toolchain pins with `?=`:

```make
TS_TOOLCHAIN_PRETTIER_VERSION ?= 3.9.6
TS_TOOLCHAIN_ZOD_VERSION ?= 4.5.4
```

Make treats an environment variable as already-defined, so `TS_TOOLCHAIN_PRETTIER_VERSION=3.0.0 make test-ts-gates` installs and gates against a formatter other than the one the emitter is calibrated to, while the mandatory gate still reports green.

## The sharper version, found while verifying it

The `?=` is not the widest door. `resolve_prettier()` in `tests/helpers/ts_toolchain.py` takes whatever `prettier` is first on `PATH` and never compares it to the pin. `make test-ts-gates` prepends the provisioned binary, so the target is safe — but running the codegen suite directly with `PIPELEX_REQUIRE_TS_GATES=1` and an ambient prettier gates the emission against an arbitrary version. The dangerous direction is a false pass: a prettier that accepts bytes the pinned one would rewrite.

## Why it deferred

- `?=` is this repo's own idiom for an overridable default (`PYTHON_VERSION ?= 3.13`, `HEARTBEAT_INTERVAL ?= 20`, `LINT_PYTHON_VERSION ?=`), and here it is the deliberate hook for probing a newer prettier before moving the pin — which is exactly the workflow the pin's documentation asks for.
- CI sets neither variable and always goes through `make test-ts-gates`, so the gate that decides whether a branch merges always runs the pin. The exposure is a developer's local run, where a false pass is caught by CI on push.
- Closing it means a third environment variable carrying the pin from the Makefile into Python plus a version-comparison branch, to guard a case the layering already handles. That is a guard on a state that cannot occur where it would matter.

## The shape of the fix, if it is ever wanted

Keep the Makefile as the single source of the pin and pass it down — `PIPELEX_PRETTIER_VERSION_PIN=$(TS_TOOLCHAIN_PRETTIER_VERSION)` beside the two variables the target already exports — then have `resolve_prettier()` compare `prettier --version` against it and refuse **only in required mode**. Duplicating the version into Python instead would create a second source of truth and is the wrong trade.

Worth revisiting if the gate ever produces a confusing result that turns out to be a version mismatch, or if a second consumer starts running these gates outside the make target.

## The same hole on the zod side

Raised in the pre-landing review of the same PR (2026-09-02). Everything above reasons about prettier, but `resolve_zod_package()` has the identical shape: with `PIPELEX_ZOD_PACKAGE` unset it falls back to `npm root -g` plus `zod` and never compares what it finds against `TS_TOOLCHAIN_ZOD_VERSION`. The deferral reasoning carries over unchanged — CI always goes through `make test-ts-gates`, which names the provisioned package explicitly — and the exposure is milder still: the round trip *executes* the schema, so a zod far enough from the pin to matter fails loudly rather than passing on bytes the pinned one would reject. If the fix above is ever taken, it should carry both pins down, not just prettier's.
