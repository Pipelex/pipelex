export const meta = {
  name: 'kw-only-fix-callsites',
  description: 'Converge step: file-disjoint fixers fix broken call sites + override impls flagged by pyright after the keyword-only signature edits. Fixers run in sequential chunks to stay under the server-side rate limit.',
  phases: [{ title: 'Fix', detail: 'one fixer per file bucket, sequential chunks' }],
}

const ROOT = '/Users/lchoquel/repos/Pipelex/_calls'
const bucketsPath = (args && args.bucketsPath) || '/tmp/wave5_fix_buckets.json'
const CHUNK = (args && args.chunk) || 5

const BUCKETS_SCHEMA = {
  type: 'object',
  required: ['buckets'],
  properties: {
    buckets: {
      type: 'array',
      items: {
        type: 'array',
        items: {
          type: 'object',
          required: ['path', 'errors'],
          properties: {
            path: { type: 'string' },
            errors: {
              type: 'array',
              items: {
                type: 'object',
                required: ['line', 'rule', 'msg'],
                properties: {
                  line: { type: 'number' },
                  rule: { type: 'string' },
                  msg: { type: 'string' },
                },
              },
            },
          },
        },
      },
    },
  },
}

const FIX_SCHEMA = {
  type: 'object',
  required: ['results'],
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        required: ['path', 'fixed', 'status'],
        properties: {
          path: { type: 'string' },
          fixed: { type: 'number' },
          status: { enum: ['fixed', 'partial', 'no-change', 'blocked'] },
          note: { type: 'string' },
        },
      },
    },
  },
}

function fixerPrompt(bucket) {
  const fileBlocks = bucket
    .map((f) => {
      const errs = f.errors.map((e) => '    L' + e.line + ' [' + e.rule + '] ' + e.msg).join('\n')
      return 'FILE: ' + f.path + '\n  PYRIGHT ERRORS:\n' + errs
    })
    .join('\n\n')
  return [
    'Repo root: ' + ROOT + '. You OWN exactly the files listed below and may edit ONLY them. You MAY read any other file (especially a callee or base class) to learn the exact signature, but edit nothing outside your owned files.',
    '',
    'CONTEXT: This is the keyword-only-arguments refactor (Wave 5). Function/method signatures were just changed so that every parameter after the subject is keyword-only (a bare `*` was inserted right after the subject). That broke the call sites and override impls listed below. Your job is to fix EACH listed pyright error by editing the CALL SITE or the OVERRIDE signature in your owned files — NOT by changing the (already-correct) callee signatures.',
    '',
    'HOW TO FIX EACH ERROR CLASS:',
    '- `reportCallIssue` ("Expected N positional arguments" / "No parameter named ..." / argument-count errors): the callee is now keyword-only after its subject. OPEN the callee definition (read its file) to get the EXACT parameter names and which one is the subject (the first param, which may stay positional). Then at the call site, convert every argument passed positionally BEYOND the subject into keyword form `name=value`, matching the callee parameter names exactly. Keep the subject positional if it already is. Do not reorder or rename anything else.',
    '- `reportIncompatibleMethodOverride` (parameter "X" is missing in override / positional count mismatch): the BASE/Protocol method was made keyword-only. OPEN the base class/Protocol, read its exact new signature, and align THIS override to match it EXACTLY — insert the bare `*` in the same position so the override is Liskov-compatible. Add `@override` only if the base already had it and it is missing here; otherwise just fix the `*` placement.',
    '',
    'RULES:',
    '- Only edit your owned files. Reading other files to learn signatures is required and encouraged.',
    '- Do NOT change any callee/base signature — those are intentional. Fix the consumer side only.',
    '- Preserve behavior, argument order, names, and types. A positional arg becomes `param_name=<same expression>`.',
    '- If a `reportCallIssue` is actually because the callee is a framework/interpreter callback that should NOT have been made keyword-only, do NOT work around it at the call site — mark the file "blocked" and explain in note (I will handle the signature). This should be rare.',
    '- After editing, the listed errors for your files should be resolved. You cannot run pyright; just fix every listed error carefully by reading the relevant signatures.',
    '',
    'Files you own and their errors:',
    fileBlocks,
    '',
    'Return {results:[{path, fixed, status, note}]} — one entry per owned file. `fixed` = number of errors you addressed in that file.',
  ].join('\n')
}

phase('Fix')
const data = await agent(
  'Read the JSON file at ' + bucketsPath + ' and return its contents EXACTLY. Shape: {buckets:[ [ {path, errors:[{line,rule,msg}]} ] ]}. Keep paths, line numbers, rules, and messages verbatim. Do not edit anything.',
  { label: 'load:buckets', phase: 'Fix', schema: BUCKETS_SCHEMA }
)
const buckets = (data && data.buckets) || []
if (!buckets.length) {
  log('No buckets — nothing to fix')
  return { buckets: 0, failed: 0, files_total: 0, by_status: {}, attention: [] }
}
log('Wave 5 converge: ' + buckets.length + ' file-disjoint fixers in chunks of ' + CHUNK)
const out = []
for (let start = 0; start < buckets.length; start += CHUNK) {
  const chunk = buckets.slice(start, start + CHUNK)
  const chunkNo = Math.floor(start / CHUNK) + 1
  log('Chunk ' + chunkNo + ': fixers ' + (start + 1) + '–' + (start + chunk.length))
  const chunkOut = await parallel(
    chunk.map((b, ci) => () => agent(fixerPrompt(b), { label: 'fix:b' + (start + ci + 1), phase: 'Fix', schema: FIX_SCHEMA }))
  )
  out.push(...chunkOut)
}
const ok = out.filter(Boolean)
const all = ok.flatMap((r) => r.results || [])
const byStatus = {}
for (const r of all) byStatus[r.status] = (byStatus[r.status] || 0) + 1
const attention = all.filter((r) => r.status === 'blocked' || r.status === 'partial')
const failed = out.filter((r) => !r).length

return {
  buckets: buckets.length,
  failed,
  files_total: all.length,
  by_status: byStatus,
  attention,
}
