# TypeScript Emission Gates

The `ts-zod` target promises something stronger than "the generated code compiles": it promises the bytes are already what Prettier would write. A codegen stamp is a raw SHA-256 over the body, so a consumer's first `prettier --write` over a generated tree that is *nearly* right rewrites it, and `pipelex codegen check` then reports an untouched file as **hand-edited** — accusing the user of the one thing they did not do. That contract is stated for consumers in [Codegen Projections](../under-the-hood/codegen-projections.md#typescript-assumes-prettiers-defaults); this page is how we hold ourselves to it.

## Why the always-on tests are not enough

`tests/unit/pipelex/codegen/test_emitted_artifacts_are_lint_clean.py` carries a set of TypeScript invariants that need no toolchain at all: no collapsible blank-line run, no line past the print width, no trailing whitespace, and no line ending inside an unterminated string literal. They are cheap, they run everywhere, and they are all **structural** — they measure the shape of the emitted lines without ever reading them as TypeScript.

That leaves a whole family of defect invisible. A member chain broken where Prettier would have kept it flat, a string literal in the quote style Prettier rewrites, an object literal spelled as JSON — each of those is a run of short, well-formed, whitespace-clean lines. Three such defects reached pull-request review, and each was caught afterwards only because somebody read the emission by hand and then wrote a byte assertion for that one shape. Hand-written assertions do not generalize to the next shape.

## The two gates that read the emission

Two tests do more than measure lines, and both need node:

| Test | What it proves |
|---|---|
| `test_emitted_ts_is_prettier_clean` | `prettier --check` over the emitted `types.ts` and `binder.ts`. It parses the emission, so it is also the syntax gate, and it holds the byte-for-byte formatting the stamp depends on. |
| `test_the_emitted_schema_parses_the_runtime_payload` | The emitted schema, under a real zod, against the JSON the runtime actually puts on the wire. It is the only layer that *executes* the projection. |

Both were written to `pytest.skip` when the toolchain was absent — which, in a Python repo whose CI installs no node, meant they skipped in CI and on every developer machine. The gates existed and guarded nothing.

## `make test-ts-gates`

The fix is not another assertion, it is making the skip impossible where it matters:

```bash
make test-ts-gates   # alias: make ttg
```

It provisions a pinned toolchain into the gitignored `.ts-toolchain/` (`make ts-toolchain` on its own does just that step), puts `prettier` on `PATH`, points `PIPELEX_ZOD_PACKAGE` at the installed `zod`, and runs the whole `tests/unit/pipelex/codegen` suite with **`PIPELEX_REQUIRE_TS_GATES=1`**. Under that flag `tests/helpers/ts_toolchain.py` turns a missing binary into a test *failure* instead of a skip, so the gates cannot lapse back into silence. The `Tests (ts emission gates)` job in `.github/workflows/tests-check.yml` runs this exact target behind `actions/setup-node`, and the `Tests (all)` aggregate requires it.

Without the flag — an ordinary `make agent-test` on a machine with no node — the two gates still skip, and say which command would provision them. The structural invariants hold the line there.

## The pins, and why moving one is an emitter change

`TS_TOOLCHAIN_PRETTIER_VERSION` and `TS_TOOLCHAIN_ZOD_VERSION` in the `Makefile` are exact. Both packages have zero dependencies, so `npm install` is reproducible without a lockfile.

The Prettier pin is not a routine dependency bump. `pipelex/codegen/emitters/ts_zod.py` models that formatter's behaviour directly — its member-chain break rule, its re-measurement of each call at the new indent, its quote-style rule, its object-literal brace padding and key unquoting. Moving the pin is a statement that the emitter now targets a different formatter, so expect the gate to red and expect to teach the emitter what changed. That is the gate working, not the gate misfiring.

Node itself needs **>= 22.6**, for `--experimental-strip-types`: it is what lets the round-trip driver run the emitted `.ts` with no build step.

## What is still not gated

`tsc --strict` over the emission is not run. It would catch a class the two gates above miss — a declared type that disagrees with the schema's inferred output on the recursive-concept path, where `z.ZodType<Name>` stops typechecking. Adding it is worthwhile and is deliberately not done here, because the recursive declared-type path has a known open defect of its own (its line overflows the print width, which the current width guard cannot be pointed at without reddening shapes Prettier already tolerates). A `tsc` gate belongs with the fix for that path, not before it.
