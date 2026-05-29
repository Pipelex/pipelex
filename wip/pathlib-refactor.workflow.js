export const meta = {
  name: 'pathlib-refactor',
  description: 'Refactor filesystem path handling to pathlib.Path, converting to/from str only at boundaries (CLI, API, env)',
  whenToUse: 'When you want to modernize path handling across pipelex/: use pathlib.Path internally, str only at boundaries.',
  phases: [
    { title: 'Inventory', detail: 'parallel read-only scan of each subsystem for filesystem-path handling' },
    { title: 'Plan', detail: 'synthesize disjoint, self-contained refactor clusters' },
    { title: 'Implement', detail: 'one agent per cluster applies pathlib idioms' },
    { title: 'Verify', detail: 'make agent-check + targeted path tests, with repair loop' },
  ],
}

// ---------------------------------------------------------------------------
// Shared guidance — every agent must respect these rules.
// ---------------------------------------------------------------------------
const RULES = `
PROJECT: pipelex (Python runtime). CWD is the repo root (a worktree on branch refactor/Paths).
GOAL: modern, pythonic filesystem-path handling.
  - Use \`from pathlib import Path\` and Path objects for ALL filesystem path manipulation internally.
  - Replace os.path.join/dirname/basename/exists/isdir/abspath/relpath, os.makedirs, os.walk, os.listdir,
    string concatenation of paths, and str-typed FS path params with Path equivalents
    (Path / "x", p.parent, p.name, p.exists(), p.is_dir(), p.resolve(), p.relative_to(), p.mkdir(parents=True, exist_ok=True),
     Path.rglob/iterdir/walk, etc.).
  - Convert to/from str ONLY at genuine boundaries: CLI argument parsing (typer/click), API request/response models,
    environment-variable parsing (os.environ, PIPELEXPATH split on os.pathsep), serialization to JSON/TOML,
    and third-party library calls that demand str. At those boundaries, str(path) / Path(raw_str) is correct and expected.
  - Internal utility functions (e.g. in pipelex/tools/misc/) should take and pass Path. Per project policy there is
    NO backward-compat requirement — change signatures directly; do NOT add \`str | Path\` unions just to be safe.
    Exception: a function that is a public exported API surface OR a boundary may keep str. Use judgment and note it.

CRITICAL — DO NOT TOUCH non-filesystem "paths". These look like paths but are NOT files on disk:
  - dotted/attribute paths: variable_path, dotted_path, var_path, from_path (blueprint refs), key_path, json paths,
    "report.pdf"-style template variable references, module import paths (a.b.c), concept/pipe paths.
  - URL paths, route paths, API endpoint paths.
  - module-path<->file-path conversion helpers where the "module path" side is dotted.
  If a *_path symbol is not an actual location on the filesystem, LEAVE IT ALONE and record it as excluded.

Be precise. Prefer correctness over breadth. Read the actual code before judging.
`

const INVENTORY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['area', 'files', 'notes'],
  properties: {
    area: { type: 'string' },
    files: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['path', 'role', 'fs_path_symbols', 'excluded_logical_paths', 'recommended_changes'],
        properties: {
          path: { type: 'string', description: 'repo-relative file path' },
          role: { type: 'string', enum: ['core_util', 'boundary', 'internal', 'test'] },
          fs_path_symbols: {
            type: 'array',
            description: 'Genuine filesystem-path functions/params/attrs that should move to Path',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['name', 'kind', 'detail'],
              properties: {
                name: { type: 'string' },
                kind: { type: 'string', enum: ['function', 'method', 'param', 'attribute', 'local', 'os_path_call'] },
                detail: { type: 'string', description: 'current signature/usage + line refs + what should change' },
              },
            },
          },
          excluded_logical_paths: {
            type: 'array',
            description: 'Symbols that look like paths but are NOT filesystem paths — must not be changed',
            items: {
              type: 'object',
              additionalProperties: false,
              required: ['name', 'reason'],
              properties: { name: { type: 'string' }, reason: { type: 'string' } },
            },
          },
          recommended_changes: { type: 'string' },
        },
      },
    },
    notes: { type: 'string', description: 'cross-file observations, especially callers of functions whose signatures should change' },
  },
}

const PLAN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['clusters', 'excluded', 'summary'],
  properties: {
    clusters: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['id', 'title', 'rationale', 'files', 'instructions', 'signature_changes'],
        properties: {
          id: { type: 'string', description: 'short kebab id, e.g. core-file-utils' },
          title: { type: 'string' },
          rationale: { type: 'string' },
          files: { type: 'array', items: { type: 'string' }, description: 'ALL files this cluster edits — MUST be disjoint from every other cluster' },
          instructions: { type: 'string', description: 'precise per-cluster refactor instructions' },
          signature_changes: { type: 'array', items: { type: 'string' }, description: 'function signatures changing, so the owning agent updates every caller within this cluster' },
        },
      },
    },
    excluded: { type: 'array', items: { type: 'string' }, description: 'logical/non-fs paths confirmed left untouched' },
    summary: { type: 'string' },
  },
}

const CLUSTER_RESULT_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['cluster_id', 'files_changed', 'summary', 'follow_ups'],
  properties: {
    cluster_id: { type: 'string' },
    files_changed: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
    follow_ups: { type: 'array', items: { type: 'string' }, description: 'anything left undone or risky for verification to watch' },
  },
}

const VERIFY_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['passed', 'commands_run', 'failures', 'raw_tail'],
  properties: {
    passed: { type: 'boolean' },
    commands_run: { type: 'array', items: { type: 'string' } },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['tool', 'file', 'message'],
        properties: {
          tool: { type: 'string', description: 'pyright | mypy | ruff | pytest | other' },
          file: { type: 'string' },
          message: { type: 'string' },
        },
      },
    },
    raw_tail: { type: 'string', description: 'last ~60 lines of combined output for context' },
  },
}

const REPAIR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['files_changed', 'notes'],
  properties: {
    files_changed: { type: 'array', items: { type: 'string' } },
    notes: { type: 'string' },
  },
}

// ---------------------------------------------------------------------------
// Phase 1 — Inventory (parallel, read-only)
// ---------------------------------------------------------------------------
phase('Inventory')

const AREAS = [
  { area: 'core-utils', scope: 'pipelex/tools/misc/ (file_utils.py, toml_utils.py, json_utils.py, base64_utils.py, filetype_utils.py, diff.py, toml_sync.py) and pipelex/tools/ broadly. This is the HUB — most FS path helpers live here.' },
  { area: 'cli', scope: 'pipelex/cli/ (commands/, agent_cli/, init/). Boundary-heavy: typer/click args are str and convert to Path here.' },
  { area: 'tracing-observer', scope: 'pipelex/tracing/ (ndjson_event_log.py) and pipelex/observer/ (local_observer.py).' },
  { area: 'system-config', scope: 'pipelex/system/ — especially environment.py (PIPELEXPATH / os.pathsep parsing — a boundary) and configuration/.' },
  { area: 'temporal-plugins', scope: 'pipelex/temporal/ (worker_cli.py) and pipelex/plugins/ (mistral_factory.py and others).' },
  { area: 'rest-of-src', scope: 'Everything else under pipelex/ NOT covered above: kit/, graph/, builder/, core/, pipe_operators/, pipe_controllers/, etc. Watch hard for logical/dotted paths here (variable_path, dotted_path, from_path) which must be EXCLUDED.' },
  { area: 'tests', scope: 'tests/ — find call sites of FS path utilities and any direct FS path handling that will need updating when signatures change. Include tests/helpers/paths.py.' },
  { area: 'export-surface', scope: 'Public export surface: pipelex/__init__.py and any re-exports, plus build a caller index. Use grep to list ALL callers across pipelex/ and tests/ of these functions: save_text_to_path, save_bytes_to_binary_file, load_text_from_path, failable_load_text_from_path, load_binary, load_binary_async, copy_file, copy_file_from_package, copy_folder_from_package, remove_file, remove_folder, mirror_dir, ensure_directory_exists, ensure_path, ensure_directory_for_file_path, get_incremental_directory_path, load_toml_from_path, save_toml_to_path. Report which of these are publicly exported (boundary) vs internal, and the full caller list per function.' },
]

const inventories = (await parallel(AREAS.map((a) => () =>
  agent(
    `${RULES}\n\nYou are inventorying area "${a.area}".\nSCOPE: ${a.scope}\n\n` +
    `Search this scope thoroughly (grep for os.path, "import os", os.makedirs/walk/listdir/getcwd, open(, *_path: str, *_dir: str, *_file: str, string path concatenation). ` +
    `For each relevant file, READ the actual usage and classify every path-like symbol as a genuine filesystem path (record in fs_path_symbols) or a logical/non-fs path (record in excluded_logical_paths with the reason). ` +
    `Note callers of any function whose signature should change. Do NOT edit anything — this is read-only.`,
    { agentType: 'Explore', schema: INVENTORY_SCHEMA, label: `inv:${a.area}`, phase: 'Inventory' },
  ),
))).filter(Boolean)

log(`Inventory complete: ${inventories.length} areas, ${inventories.reduce((n, i) => n + (i.files?.length || 0), 0)} files flagged`)

// ---------------------------------------------------------------------------
// Phase 2 — Plan (single synthesizer; barrier — needs the full inventory)
// ---------------------------------------------------------------------------
phase('Plan')

const plan = await agent(
  `${RULES}\n\nYou are the refactor architect. Below is the full filesystem-path inventory of the repo as JSON.\n\n` +
  `${JSON.stringify(inventories, null, 2)}\n\n` +
  `Produce a refactor plan as a set of CLUSTERS with these HARD constraints:\n` +
  `1. Clusters must partition the work into DISJOINT file sets — NO file may appear in two clusters. If a file (e.g. a test or CLI module) calls utilities from what would be two clusters, MERGE those clusters so one agent owns all coupled files.\n` +
  `2. Each cluster must be SELF-CONTAINED: if it changes a function signature, it must include that function's definition AND every caller of it (across pipelex/ and tests/). This is why disjointness matters — it guarantees parallel agents never touch the same file and signatures stay consistent.\n` +
  `3. Group naturally: a "core-file-utils" cluster (file_utils.py + all its callers) will likely be the largest and that is fine — one agent owns it.\n` +
  `4. Confirm the excluded logical/non-fs paths so implementers know what to leave alone.\n` +
  `5. Verify caller completeness yourself with grep before finalizing — do not rely solely on the inventory notes.\n` +
  `Order clusters by importance but assume they are independent (they will run in parallel). Write precise, actionable per-cluster instructions.`,
  { schema: PLAN_SCHEMA, label: 'synthesize-plan', phase: 'Plan' },
)

// Safety net: detect any file that leaked into >1 cluster and warn (synthesis is instructed to avoid this).
const seen = {}
const collisions = new Set()
for (const c of plan.clusters) for (const f of (c.files || [])) { if (seen[f]) collisions.add(f); seen[f] = true }
if (collisions.size) log(`WARNING: ${collisions.size} file(s) appear in multiple clusters: ${[...collisions].join(', ')} — running sequentially-safe is NOT guaranteed; review.`)
log(`Plan: ${plan.clusters.length} clusters covering ${Object.keys(seen).length} files. ${plan.summary}`)

// ---------------------------------------------------------------------------
// Phase 3 — Implement (parallel, one agent per cluster; disjoint file sets)
// ---------------------------------------------------------------------------
phase('Implement')

const results = (await parallel(plan.clusters.map((c) => () =>
  agent(
    `${RULES}\n\nYou OWN this refactor cluster and ONLY these files — do not edit files outside the list:\n` +
    `${JSON.stringify(c.files, null, 2)}\n\n` +
    `Title: ${c.title}\nRationale: ${c.rationale}\nSignature changes you must propagate to every caller in your file list: ${JSON.stringify(c.signature_changes)}\n\n` +
    `Instructions:\n${c.instructions}\n\n` +
    `Apply the edits with the Edit/Write tools. Keep changes idiomatic and minimal — convert genuine FS path handling to pathlib.Path, keep str only at the boundaries described in the rules. ` +
    `Do not run linters or tests (a dedicated verify phase does that). When done, report exactly which files you changed.`,
    { schema: CLUSTER_RESULT_SCHEMA, label: `impl:${c.id}`, phase: 'Implement' },
  ),
))).filter(Boolean)

const changedFiles = [...new Set(results.flatMap((r) => r.files_changed || []))]
log(`Implementation complete: ${results.length} clusters, ${changedFiles.length} files changed.`)

// ---------------------------------------------------------------------------
// Phase 4 — Verify + repair loop (barrier; whole-repo lint/type check)
// ---------------------------------------------------------------------------
phase('Verify')

const VERIFY_CMDS =
  'Run, from the repo root, IN THIS ORDER and capture output:\n' +
  '  1. `make agent-check`  (ruff fix-unused-imports + format + lint, then pyright, then mypy)\n' +
  '  2. `.venv/bin/pytest -q -p no:randomly -m "not (inference or pipelex_api or imgg or gha_disabled or needs_output or llm or ocr)" -k "test_boot or test_toml_utils or test_paths or inputs_path_resolver or convert_file_path_to_module_path" --tb=short`  (targeted: boot/config load + path-related unit tests)\n' +
  'Report passed=true ONLY if make agent-check exits 0 AND the targeted pytest exits 0. ' +
  'Parse failures into the structured list (tool, file, message). Include the last ~60 lines of combined output in raw_tail.'

let verify = await agent(
  `You are the verification gate for a pathlib refactor. ${VERIFY_CMDS}`,
  { schema: VERIFY_SCHEMA, label: 'verify:1', phase: 'Verify' },
)

let attempt = 0
while (!verify.passed && attempt < 3) {
  attempt++
  log(`Verify failed (attempt ${attempt}): ${verify.failures.length} issue(s). Repairing...`)
  await agent(
    `${RULES}\n\nThe pathlib refactor introduced check/test failures. Fix them at the ROOT cause — keep the pathlib best-practice intent; ` +
    `do NOT revert to os.path just to silence a checker unless the location is a genuine boundary. ` +
    `If a failure reveals a misclassified logical (non-fs) path that should never have been changed, revert that specific change.\n\n` +
    `Failures (JSON):\n${JSON.stringify(verify.failures, null, 2)}\n\nRaw output tail:\n${verify.raw_tail}\n\n` +
    `Edit the offending files to fix every failure. Do not run the full check yourself; the gate will re-run.`,
    { schema: REPAIR_SCHEMA, label: `repair:${attempt}`, phase: 'Verify' },
  )
  verify = await agent(
    `You are the verification gate for a pathlib refactor (re-run after repair attempt ${attempt}). ${VERIFY_CMDS}`,
    { schema: VERIFY_SCHEMA, label: `verify:${attempt + 1}`, phase: 'Verify' },
  )
}

log(verify.passed ? 'Verification PASSED ✅' : `Verification still FAILING after ${attempt} repair attempt(s) ❌`)

return {
  inventory_summary: { areas: inventories.length, files_flagged: inventories.reduce((n, i) => n + (i.files?.length || 0), 0) },
  plan_summary: plan.summary,
  excluded_logical_paths: plan.excluded,
  clusters: plan.clusters.map((c) => ({ id: c.id, title: c.title, files: c.files })),
  files_changed: changedFiles,
  implementation: results,
  verification: verify,
}
