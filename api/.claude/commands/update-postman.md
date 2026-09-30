# Update Postman Collection

You update the **Pipelex FastAPI** collection directly in the user's Postman desktop app via the Postman API. You take an incremental, diff-based approach: read what's already in Postman, compare against the current API state, and only change what's needed.

**You do NOT write JSON files to the repo.** You push changes directly to Postman using `https://api.getpostman.com`.

## Constants

- **Collection UID**: `35082494-559c5753-885c-409a-af63-7647fe28d301`
- **Collection name**: `Pipelex FastAPI`
- **Postman API base**: `https://api.getpostman.com`
- **Local API**: `http://127.0.0.1:8081`
- **Auth token for local testing**: `test-api-key`

## Prerequisites

You need the `POSTMAN_API_KEY` environment variable. **Always** run `source ~/.zshrc 2>/dev/null` before any command that uses it.

If `POSTMAN_API_KEY` is not set after sourcing, tell the user:
> I need your Postman API key. Generate one in Postman: **Settings > API keys > Generate API Key**. Then add to `~/.zshrc`:
> ```
> export POSTMAN_API_KEY="your-key-here"
> ```

## Steps

### 1. Fetch the current collection from Postman

```bash
source ~/.zshrc 2>/dev/null
curl -s -H "X-API-Key: $POSTMAN_API_KEY" \
  "https://api.getpostman.com/collections/35082494-559c5753-885c-409a-af63-7647fe28d301" \
  > /tmp/postman_current.json
```

Parse and inventory the current state using Python — list every folder, request name, URL path, and method. This is your **baseline**.

```bash
python3 -c "
import json
with open('/tmp/postman_current.json') as f:
    data = json.load(f)
col = data['collection']

def inventory(items, prefix=''):
    for item in items:
        if 'item' in item:
            print(f\"{prefix}[folder] {item['name']} ({len(item['item'])} items)\")
            inventory(item['item'], prefix + '  ')
        elif 'request' in item:
            r = item['request']
            method = r.get('method', '?')
            print(f\"{prefix}{method} {item['name']}\")

inventory(col['item'])
"
```

If the collection does not exist (404), the baseline is empty — you'll create it from scratch with `POST /collections` at the end.

### 2. Discover what changed in the code

Run `git diff main...HEAD --name-only` to see which files changed on the current branch.
If $ARGUMENTS contains a PR number, use `gh pr diff <number>` instead.

Categorize the changed files:
- **Route files** (`api/routes/**/*.py`, `api/main.py`) → endpoints may have been added, removed, or modified
- **Schema files** (`api/schemas/models.py`) → request/response shapes may have changed
- **Security** (`api/security.py`) → auth behavior may have changed
- **Other files** → likely no Postman impact

If NO route/schema/security files changed, tell the user "No API changes detected — Postman collection is already up to date" and stop.

### 3. Read the changed route files

Only read the route files that actually changed (from step 2). Also read:
- `api/routes/__init__.py` and any `__init__.py` in the hierarchy — to check if routers were added/removed
- `api/main.py` — to check if prefix structure changed

Glob `api/routes/**/*.py` to detect any **new** route files not yet in Postman.

### 4. Determine what needs to change

Compare the Postman baseline (step 1) against the code (step 3):

- **New endpoints** — route exists in code but no matching request in Postman
- **Removed endpoints** — request exists in Postman but route was deleted from code
- **Modified endpoints** — route file changed; check if method, path, request body schema, query params, or response shape differ
- **Unchanged endpoints** — leave these exactly as they are (preserve user edits!)

Produce a clear **change plan** and show it to the user before proceeding:
```
Changes to apply:
  + ADD: POST /v1/new-endpoint (folder: Build)
  ~ UPDATE: POST /v1/build/pipe-spec — request body changed (added "model" field)
  - REMOVE: POST /v1/build/pipe — endpoint deleted
  = UNCHANGED: 28 requests
```

### 5. Fetch the OpenAPI spec for changed endpoints

Only needed for endpoints that are new or modified.

Check if the API is running: `curl -s http://127.0.0.1:8081/health`
If not running, start it: `make run` (runs in background) and wait a few seconds.

Fetch `http://127.0.0.1:8081/openapi.json` to get the ground truth:
- Exact parameter names and types
- Enum values (e.g., format uses lowercase `schema`, `json`, `python` — NOT uppercase)
- Required vs optional fields
- Response shapes

### 6. Test changed endpoints against the running API

Only test endpoints that are **new or modified**. For each, curl with:
- A happy-path request → capture the real response shape
- An error request → capture the error format

Always use `-H "Authorization: Bearer test-api-key"` for authenticated endpoints.

### 7. Build examples for new/modified endpoints

For **new endpoints**, create rich examples following the rules below.
For **modified endpoints**, update existing examples to match the new schema while preserving intent.
For **unchanged endpoints**, do NOT touch them.

#### Example rules:
- Each endpoint must have at least one **happy path** and one **error** example
- Use realistic, meaningful data — never "test", "foo", "bar"
- All examples must be **self-contained** and **copy-pasteable**
- Response bodies must match **actual API responses** (from step 6)
- Read `postman/examples/` for `.mthds` files and `results/pipe-builder/` for real-world examples

#### Pipe type diversity — for endpoints accepting `mthds_contents`:
1. **PipeLLM** — text analysis, summarization, Q&A
2. **PipeExtract** — structured data extraction
3. **PipeSequence** — multi-step pipeline
4. **PipeCompose** — combining concepts
5. **PipeCondition** — branching on a field value
6. **PipeParallel** — concurrent pipe execution
7. **PipeBatch** — iterating over a list

#### Endpoint-specific minimums:

| Endpoint | Required examples |
|---|---|
| Pipeline Execute/Start | 1 per pipe type, 1 pipe_code only, 1 error |
| Validate | 1 valid, 1 missing main_pipe error |
| Build Inputs | 1 happy path, 1 pipe not found error |
| Build Output | 1 per format (`schema`, `json`, `python`) |
| Build Runner | 1 happy path, 1 error |
| Build Concept | structured fields, refines, concept_ref, 1 error |
| Build Pipe Spec | 1 per pipe type, 1 invalid type error |
| Models | no filter, filter by `llm`, filter by `extract`, multi-type |
| Presigned Post URLs | single file, multiple files |
| Version | version (protocol handshake) |

### 8. Apply changes to the collection using Python

Use a Python script to modify the collection JSON in `/tmp/postman_current.json`. This is the proven pattern:

```bash
python3 << 'PYEOF'
import json

with open('/tmp/postman_current.json') as f:
    data = json.load(f)

col = data['collection']

# Navigate to the right folder
# Example: find Agent > Build Pipe Spec
for folder in col['item']:
    if folder['name'] == 'Agent':
        for sub in folder['item']:
            if sub['name'] == 'Build Pipe Spec':
                target = sub
                break

# Build the new request item
new_item = {
    "name": "PipeCondition — route by match score",
    "request": {
        "method": "POST",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {
            "mode": "raw",
            "raw": json.dumps({...}, indent="\t")
        },
        "url": {
            "raw": "{{base_url}}/v1/build/pipe-spec",
            "host": ["{{base_url}}"],
            "path": ["v1", "build", "pipe-spec"]
        },
        "description": "..."
    },
    "response": [
        {
            "name": "200 OK",
            "originalRequest": {"method": "POST", "url": {"raw": "{{base_url}}/v1/build/pipe-spec", "host": ["{{base_url}}"], "path": ["v1", "build", "pipe-spec"]}},
            "status": "OK",
            "code": 200,
            "body": json.dumps({...})
        }
    ]
}

# Insert before the error example (usually last)
error_idx = len(target['item']) - 1
target['item'].insert(error_idx, new_item)

# For removals: target['item'] = [i for i in target['item'] if i['name'] != 'Old Item']
# For updates: find the item by name and replace its request/response

with open('/tmp/postman_updated.json', 'w') as f:
    json.dump(data, f)

print("Ready to push")
PYEOF
```

Key patterns:
- **Add**: `folder['item'].insert(position, new_item)` — insert before the error example
- **Remove**: filter out by name
- **Update**: find by name, replace `request` and/or `response` keys
- **New folder**: `{"name": "New Folder", "item": [...]}`
- Always use `json.dumps(body, indent="\t")` for request body `raw` field

#### Collection structure rules:
- Auth: Bearer with `{{auth_token}}`
- Variables: `base_url`, `auth_token`
- All URL paths use `{{base_url}}` prefix
- `{ "type": "noauth" }` for health/root endpoints only

#### Folder organization:
- `Health & Info` → `Root`, `Health Check`
- `Version` → version (protocol handshake)
- `Pipeline` → `Execute (sync)`, `Start (async)`
- `Validate` → with valid/invalid sub-examples
- `Build` → `Build Inputs`, `Build Output`, `Build Runner`
- `Agent` → `Build Concept`, `Build Pipe Spec`, `Models`
- `Uploader` → `Presigned Post URLs`

### 9. Push to Postman

```bash
source ~/.zshrc 2>/dev/null
curl -s -X PUT \
  -H "X-API-Key: $POSTMAN_API_KEY" \
  -H "Content-Type: application/json" \
  -d @/tmp/postman_updated.json \
  "https://api.getpostman.com/collections/35082494-559c5753-885c-409a-af63-7647fe28d301" \
  | python3 -m json.tool
```

If creating a new collection (no existing UID), use `POST /collections` instead of PUT.

**Clean up:**
```bash
rm -f /tmp/postman_current.json /tmp/postman_updated.json
```

### 10. Verify

```bash
source ~/.zshrc 2>/dev/null
curl -s -H "X-API-Key: $POSTMAN_API_KEY" \
  "https://api.getpostman.com/collections/35082494-559c5753-885c-409a-af63-7647fe28d301" \
  | python3 -c "
import json, sys
data = json.load(sys.stdin)
col = data['collection']

def count(items):
    folders = requests = 0
    for item in items:
        if 'item' in item:
            folders += 1
            f, r = count(item['item'])
            folders += f
            requests += r
        elif 'request' in item:
            requests += 1
    return folders, requests

f, r = count(col['item'])
print(f\"Collection '{col['info']['name']}' synced: {f} folders, {r} requests\")
"
```

Report a summary:
```
Postman collection updated:
  + Added: 1 request (PipeCondition — route by match score)
  = Unchanged: 34 requests
  Total: 35 requests across 19 folders
```

Changes appear in Postman desktop immediately (auto-sync).

## Important constraints

- **Do NOT write JSON files to the repo** — only use `/tmp/` for the API push, then clean up
- **Preserve user edits** — never overwrite unchanged endpoints
- **Show the change plan before pushing** — never push silently
- **Always `source ~/.zshrc 2>/dev/null`** before any command using `$POSTMAN_API_KEY`
- The Postman API expects `{"collection": {...}}` envelope — the fetched JSON already has this structure, so just modify `data['collection']` and write `data` back
- Enum values are lowercase: `schema`, `json`, `python` — NOT uppercase
- `mthds_contents` is always `list[str]`, even for a single file
