export const meta = {
  name: 'kw-only-wave5-signatures',
  description: 'Wave 5 Phase A: file-disjoint editors add a bare * after the subject to each flagged framework-sensitive/public-API function (signature edits only, no call sites). Editors run in sequential chunks to stay under the server-side rate limit.',
  phases: [{ title: 'Signatures', detail: 'editors run in sequential chunks of CHUNK, each chunk a barrier' }],
}

const ROOT = '/Users/lchoquel/repos/Pipelex/_calls'
const specPath = (args && args.specPath) || '/tmp/wave5_sig_spec.json'
const CHUNK = (args && args.chunk) || 4

const SPEC_SCHEMA = {
  type: 'object',
  required: ['editors'],
  properties: {
    editors: {
      type: 'array',
      items: {
        type: 'array',
        items: {
          type: 'object',
          required: ['path', 'funcs'],
          properties: {
            path: { type: 'string' },
            funcs: { type: 'array', items: { type: 'string' } },
          },
        },
      },
    },
  },
}

const SIG_SCHEMA = {
  type: 'object',
  required: ['results'],
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'func', 'status'],
        properties: {
          path: { type: 'string' },
          func: { type: 'string' },
          status: { enum: ['added-star', 'moved-star', 'already-ok', 'not-found', 'needs-manual'] },
          note: { type: 'string' },
        },
      },
    },
  },
}

function editorPrompt(group) {
  const fileBlocks = group
    .map((f) => 'FILE: ' + f.path + '\n  FUNCTIONS TO FIX: ' + f.funcs.join(', '))
    .join('\n')
  return [
    'Repo root: ' + ROOT + '. You OWN exactly these files and may edit ONLY them. You MAY read any other file to understand a signature, but edit nothing outside your owned files.',
    '',
    'TASK: This is the keyword-only-arguments refactor (Wave 5, framework-sensitive & public API: builder/cli/system/temporal/public-surface). For each function listed below, make every parameter AFTER the subject keyword-only by placing a bare `*` separator right after the subject parameter. These are pure SIGNATURE edits — do NOT touch any call site, do NOT change parameter names, order, types, defaults, or behavior.',
    '',
    'THE RULE precisely:',
    '- Drop any leading `self` / `cls`. The FIRST remaining parameter is the "subject" — it MAY stay positional-or-keyword.',
    '- Insert a bare `*` immediately AFTER the subject, so every following parameter becomes keyword-only. Example: `def f(a, b, c=2)` -> `def f(a, *, b, c=2)`. Keep all defaults attached to their params.',
    '- EXISTING-`*` TRAP: if the function ALREADY has a bare `*` but two-or-more positional params sit BEFORE it (e.g. `def f(a, b, *, c)`), that is STILL a violation. MOVE the `*` up to right after the subject: `def f(a, *, b, c)`. Do not just leave it.',
    '- If a function has `*args` (a starred positional) there is no separate bare `*` to add and you cannot make later params keyword-only without breaking it — mark status "needs-manual" and explain in note. Same for any case you are unsure about.',
    '- If the function turns out to already be compliant (subject + nothing else, or `*` already correctly placed right after the subject), mark "already-ok".',
    '- If you cannot find the named function in the file, mark "not-found".',
    '',
    'CRITICAL — DO NOT add `*` to a method carrying `@override` (it must match its base). None should be in your list (the guard skips them); if one is, mark "needs-manual".',
    'CRITICAL — if the function is handed to a framework/interpreter/library as a CALLBACK invoked positionally (e.g. registered as an HTTP route handler, a thread/executor target with positional `args=`, a `sys.excepthook`, a signal handler, a Jinja2 filter, an SDK callback), making its params keyword-only would break it at runtime and the type checker is BLIND to it. If you see such a registration in the same file (or strongly suspect one), mark "needs-manual" and explain — do NOT add the `*`. (The known ones — `_apply`, `_exception_handler`, `serve_until_callback`, `pytest_collection_modifyitems` — have already been removed from your list.)',
    'DO NOT edit decorators, docstrings, or logic. Multi-line signatures: keep formatting clean and valid; the project formatter will run later.',
    '',
    'Files and functions you own:',
    fileBlocks,
    '',
    'Return {results:[{path, func, status, note}]} with ONE entry per (file, function) you were asked to fix.',
  ].join('\n')
}

phase('Signatures')
const spec = await agent(
  'Read the JSON file at ' + specPath + ' and return its contents EXACTLY. It has shape {editors:[ [ {path, funcs:[...]} ] ]} — an array of editor groups, each group an array of {path, funcs}. Keep all relative paths and function names verbatim. Do not edit anything.',
  { label: 'load:spec', phase: 'Signatures', schema: SPEC_SCHEMA }
)
const editors = (spec && spec.editors) || []
if (!editors.length) {
  log('No editors in spec — nothing to do')
  return { editors: 0, failed_editors: 0, functions_total: 0, by_status: {}, attention: [] }
}
log('Wave 5 signature fan-out: ' + editors.length + ' file-disjoint editors in chunks of ' + CHUNK)
const out = []
for (let start = 0; start < editors.length; start += CHUNK) {
  const chunk = editors.slice(start, start + CHUNK)
  const chunkNo = Math.floor(start / CHUNK) + 1
  log('Chunk ' + chunkNo + ': editors ' + (start + 1) + '–' + (start + chunk.length))
  const chunkOut = await parallel(
    chunk.map((g, ci) => () => agent(editorPrompt(g), { label: 'sig:e' + (start + ci + 1), phase: 'Signatures', schema: SIG_SCHEMA }))
  )
  out.push(...chunkOut)
}
const ok = out.filter(Boolean)
const all = ok.flatMap((r) => r.results || [])
const byStatus = {}
for (const r of all) byStatus[r.status] = (byStatus[r.status] || 0) + 1
const attention = all.filter((r) => r.status === 'needs-manual' || r.status === 'not-found')
const failedEditors = out.filter((r) => !r).length

return {
  editors: editors.length,
  failed_editors: failedEditors,
  functions_total: all.length,
  by_status: byStatus,
  attention,
}
