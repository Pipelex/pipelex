export const meta = {
  name: 'kw-only-wave4-signatures',
  description: 'Wave 4 Phase A: file-disjoint editors add a bare * after the subject to each flagged execution-path function (signature edits only, no call sites).',
  phases: [{ title: 'Signatures', detail: 'one editor per file group, all in parallel' }],
}

const ROOT = '/Users/lchoquel/repos/Pipelex/_calls'
const specPath = (args && args.specPath) || '/tmp/wave4_sig_spec.json'

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
    'TASK: This is the keyword-only-arguments refactor (Wave 4, execution path). For each function listed below, make every parameter AFTER the subject keyword-only by placing a bare `*` separator right after the subject parameter. These are pure SIGNATURE edits — do NOT touch any call site, do NOT change parameter names, order, types, defaults, or behavior.',
    '',
    'THE RULE precisely:',
    '- Drop any leading `self` / `cls`. The FIRST remaining parameter is the "subject" — it MAY stay positional-or-keyword.',
    '- Insert a bare `*` immediately AFTER the subject, so every following parameter becomes keyword-only. Example: `def f(a, b, c=2)` -> `def f(a, *, b, c=2)`. Keep all defaults attached to their params.',
    '- EXISTING-`*` TRAP: if the function ALREADY has a bare `*` but two-or-more positional params sit BEFORE it (e.g. `def f(a, b, *, c)`), that is STILL a violation. MOVE the `*` up to right after the subject: `def f(a, *, b, c)`. Do not just leave it.',
    '- If a function has `*args` (a starred positional) there is no separate bare `*` to add and you cannot make later params keyword-only without breaking it — mark status "needs-manual" and explain in note. Same for any case you are unsure about.',
    '- If the function turns out to already be compliant (subject + nothing else, or `*` already correctly placed right after the subject), mark "already-ok".',
    '- If you cannot find the named function in the file, mark "not-found".',
    '',
    'DO NOT add `*` to a method carrying `@override` (it must match its base) — but none should be in your list; if one is, mark "needs-manual".',
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
log('Wave 4 signature fan-out: ' + editors.length + ' file-disjoint editors')
const out = await parallel(
  editors.map((g, gi) => () => agent(editorPrompt(g), { label: 'sig:e' + (gi + 1), phase: 'Signatures', schema: SIG_SCHEMA }))
)
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
