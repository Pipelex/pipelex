# Tracing Input Semantics

`pipelex-dev trace-input-semantics` is an internal capture harness that answers one question with evidence instead of code-reading: **what does each hop of the input-schema emission chain do to every fact a method author writes?** Given one or more `.mthds` bundle files, it loads them through the validation library and dumps per-hop captures of the chain that turns authored structure syntax into the `json_schema` emitted on `pipe_io_contracts`.

```bash
.venv/bin/pipelex-dev trace-input-semantics path/to/bundle.mthds -o output_dir
```

## What it captures

Each hop of the chain writes its captures into the output directory, so a lost or mangled fact is localized to exactly one hop:

- `hop1_bundle_blueprints.json` — **parse**: the `PipelexBundleBlueprint` dumps, i.e. what survived TOML.
- `hop2_structure_classes/` — **resolve + build**: one JSON file per traced concept describing the structure class the loaded library holds for it, read off the class itself: `class_name`, `bases`, `doc`, and for each field its annotation (`repr`), whether it is required, whether it admits `None`, its default when it has one, and its description. The class is the one the runtime built from the concept's structure at load time, or the class a `structure = "ClassName"` concept names, and concepts coming from `PIPELEXPATH` or a dependency are traced like any other. The manifest maps every traced concept to its file, and `native.Anything`, which declares no structure class, to `null`.
- `hop2_python_structures.py.txt` — the module the `python-structures` codegen emitter renders for the loaded library's crate, which is the file `pipelex build structures` would give a user, with every class named as the runtime names it (`domain__Code`). It is secondary evidence: it agrees with the runtime's class only for a concept with a structure table within that crate, and renders a structureless concept, a class-backed concept, a refinement of a concept outside the crate and a `native.Anything` field differently (see [Codegen Projections](../under-the-hood/codegen-projections.md)). The `.txt` suffix keeps the capture inert to linters.
- `hop3_raw_pydantic_schemas/` — raw `model_json_schema()` per structure class, before any Pipelex render wrapping.
- `hop4_schema_renders/` — the `SCHEMA` representation per pipe input: the `{"concept", "content"}` envelope, with array wrapping when the input is multiple.
- `hop5_pipe_io_contracts.json` — the final wire contracts from `build_pipe_io_contracts`.
- `hop5_input_form.json` — the input-form descriptors from `build_input_form`, the sibling projection that reads the authored blueprints directly instead of the emitted schema (see [Input-Form Descriptor](../under-the-hood/input-form-descriptor.md)). Captured beside the contracts so a fact can be checked on both sides: lost in the schema, stated in the descriptor.
- `trace_manifest.json` — the capture inventory plus the wire framing per pipe input: authored ref string, resolved concept ref, multiplicity, presence marker.

The tool is a tracer, not a report generator: it never mutates the loaded library, and any analysis of the captures (diffing hops, building a survival table) stays with the caller. Rerunning into the same output directory replaces the `hop2_structure_classes/`, `hop3_raw_pydantic_schemas/`, and `hop4_schema_renders/` capture directories and the `hop2_python_structures.py.txt` module wholesale, so no artifact from a removed or renamed concept, pipe, or input lingers from an earlier trace.

## When to reach for it

Use it whenever a change touches the emission chain — the structure blueprint, the structure generator, the schema render, the contract builder, or the input-form deriver — and you want to see what actually reaches the wire rather than reason about it. The committed probe bundle at `tests/data/input_semantics/probe_bundle.mthds` exercises every construct the language accepts (all field types, choices, defaults, required both ways, nesting, refinements, native concepts, and the `?` / `!` / `[]` / `[N]` input markers), and `tests/data/input_semantics/rejected/` holds deliberately-invalid fixtures pinning what the language refuses:

```bash
.venv/bin/pipelex-dev trace-input-semantics tests/data/input_semantics/probe_bundle.mthds -o /tmp/probe-trace
```

The harness was built for the S1 input-semantics audit of the input-form program. The integration test at `tests/integration/pipelex/cli/test_trace_input_semantics_cmd.py` keeps the per-hop capture format honest.
