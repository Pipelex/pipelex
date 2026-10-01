# MTHDS Tools

The MTHDS Tools endpoints expose lightweight editor tooling for a single `.mthds`
file. They are Pipelex API extensions, not MTHDS Protocol routes.

## Lint

**Endpoint:** `POST /v1/lint`

`/lint` checks one `.mthds` file with `pipelex-tools-py`. It validates fully
offline against the embedded official MTHDS schema; the request path does not
fetch schemas or read local catalog files.

### Request

- `content` (string, required): one `.mthds` file's contents
- `source` (string | null, optional): logical filename reserved for diagnostic
  locators; accepted for parity with `pipelex-tools-py`

```json
{
  "content": "domain = \"hello\"\nmain_pipe = \"echo\"\n",
  "source": "hello.mthds"
}
```

### Response

`/lint` is a diagnostic endpoint: malformed `.mthds` content returns HTTP 200
with diagnostics in the body. Request-shape problems, such as missing `content`
or a file over the configured per-file limit, return RFC 7807 problem responses.

```json
{
  "diagnostics": [
    {
      "kind": "syntax",
      "severity": "error",
      "message": "expected value",
      "location": null,
      "range": {
        "start_offset": 6,
        "end_offset": 6,
        "start_line": 1,
        "start_col": 7,
        "end_line": 1,
        "end_col": 7
      }
    }
  ]
}
```

An empty `diagnostics` array means the file is clean.

## Format

**Endpoint:** `POST /v1/format`

`/format` formats one `.mthds` file with the canonical formatter from
`pipelex-tools-py`.

### Request

- `content` (string, required): one `.mthds` file's contents
- `options` (object | null, optional): formatter options passed through to
  `pipelex-tools-py`, such as `column_width`

```json
{
  "content": "a=1",
  "options": { "column_width": 120 }
}
```

### Response

Syntax errors return HTTP 200 with the original content unchanged and diagnostics
describing the blocking issue. Malformed formatter options, such as a non-numeric
`column_width`, are caller input errors and return RFC 7807 422 responses.

```json
{
  "formatted": "a = 1\n",
  "changed": true,
  "diagnostics": []
}
```

`changed` is `true` when `formatted` differs from `content`.
