---
status: active
item: L-260925-94110e
---

# Sign `public_url` virtual-hosted, and give every normalized input a `public_url`

## The problem, verified

The item's claim holds. `S3StorageProvider._get_client_config` (`pipelex/tools/storage/s3_storage_provider.py:70-86`) builds every client with an explicit `endpoint_url = https://s3.<region>.amazonaws.com` and a `Config(signature_version="s3v4")` that names no addressing style. With an endpoint given and no style, botocore signs path-style, so every presigned `public_url` lands on the region's shared host, `https://s3.<region>.amazonaws.com/<bucket>/<key>?X-Amz-…`. A content security policy source is an origin, that origin is shared by every bucket in the region, and the MCP hosts drop the path from a path-scoped source, so no view can allow the runtime's links without allowing every bucket anyone owns in the region.

The endpoint pin has been there since the S3 provider first landed (the v0.18.0 release commit, `f069d185b`), with no recorded reason.

The measurement below was taken in this repo's venv (botocore 1.40.61, aioboto3 15.5.0), presigning `get_object` with dummy credentials; presigning makes no network call.

| Client configuration | Bucket `pipelex-app-dev` | Bucket `my.dotted.bucket` |
| --- | --- | --- |
| Today: regional endpoint, no style | `s3.us-west-2.amazonaws.com/pipelex-app-dev/…` | `s3.us-west-2.amazonaws.com/my.dotted.bucket/…` |
| Regional endpoint, `addressing_style: virtual` | `pipelex-app-dev.s3.us-west-2.amazonaws.com/…` | `s3.us-west-2.amazonaws.com/my.dotted.bucket/…` |
| No endpoint, no style | `pipelex-app-dev.s3.amazonaws.com/…` | `s3.us-west-2.amazonaws.com/my.dotted.bucket/…` |
| No endpoint, `addressing_style: virtual` | `pipelex-app-dev.s3.us-west-2.amazonaws.com/…` | `s3.us-west-2.amazonaws.com/my.dotted.bucket/…` |

Two facts come out of it. Adding the virtual style to the existing configuration yields the bucket's own regional host, which the hosted console's views already allow (`RUN_OUTPUT_SOURCES` in `pipelex-mcp/packages/console/src/hosted/app-buckets.ts:45` names both the global and the regional virtual-hosted origin of each app bucket). And a bucket name containing a dot can never be virtual-hosted over HTTPS, because the name breaks the `*.s3.<region>.amazonaws.com` wildcard certificate, so botocore falls back to path-style for it whatever the style says.

The unsigned fallback, `_make_public_url` (`s3_storage_provider.py:176-185`), already builds the virtual-hosted form, so today the signed and unsigned links disagree. It builds that form for a dotted bucket too, where it fails the TLS handshake: a pre-existing bug, fixed here.

## Nothing depends on the path-style form

The workspace was swept for consumers of the runtime's link shape:

- **pipelex-mcp** refuses the path-style host on purpose and allows both virtual-hosted forms (`app-buckets.ts`, with a test asserting the regional form is allowed). Its comments in `app-buckets.ts`, `packages/core/src/capabilities/run.ts` and `packages/console/src/views/run-results.ts` describe the runtime as signing path-style; they go stale once the hosted plane runs this fix, which is a follow-up for that repo.
- **pipelex-app** proxies whatever URL the platform resolves (`/api/assets`) and parses none; its tests use path-style URLs only as opaque fixtures.
- **pipelex-server** signs its own links independently, with boto3's default endpoint (the global virtual-hosted form), and never parses the runtime's. Its storage-resolution doc already shows the regional virtual-hosted form in an example.
- **The hosted plane's network rules** were checked, and none of them depends on the S3 hostname, so moving the runtime's own `get_object` and `put_object` calls to the bucket's host changes nothing there.
- **Bucket policies and CORS rules** apply to a bucket regardless of the addressing style a request used.

## Decisions

### One client form: virtual-hosted on the bucket's regional host

`_get_client_config` keeps its regional endpoint and adds `s3={"addressing_style": "virtual"}` to its `Config`. Every call the provider makes, the reads, the writes and the presigning, then addresses `https://<bucket>.s3.<region>.amazonaws.com`.

Two alternatives were weighed and rejected. Dropping the endpoint pin without a style would sign on the global host, `<bucket>.s3.amazonaws.com`, the platform's form, which the console also allows; but the global host reaches a bucket outside `us-east-1` only through DNS that AWS warns can answer with a temporary redirect for a newly created bucket, and the regional host has no such caveat. Applying the virtual style only to the presigning client would keep the runtime's own traffic on the shared host and limit the change to the link, at the price of two client configurations for one bucket; with nothing on the hosted plane depending on the hostname, the smaller surface wins, and virtual-hosted is AWS's recommended addressing in any case.

The risk this accepts is a self-hosted deployment whose egress proxy allows only `s3.<region>.amazonaws.com`: its reads and writes would start failing. The changelog entry names it, so an operator can widen the rule to `*.s3.<region>.amazonaws.com`.

### Signed and unsigned links follow one rule

Both forms are virtual-hosted on the bucket's regional host, except for a bucket name containing a dot, which falls back to path-style on the regional host. botocore applies that rule to the signed form by itself; `_make_public_url` applies it by hand, so an unsigned link never names a host the signed link would not. A test pins the two forms to the same host for both kinds of bucket name.

### Every normalized input carries a `public_url`

The item's second observation, the moodboard rendering as `src="None"`, traces to the runtime, not the method. `_normalize_url_content` (`pipelex/pipeline/input_normalizer.py:204`) fills `public_url` for two of the four input forms, the `data:` URL and the local path, each of which it stores and then signs. It passes an `http(s)` URL and a `pipelex-storage://` reference through untouched (`input_normalizer.py:286`), so their `public_url` stays `None`, and Jinja renders `{{ moodboard.public_url }}` as the string `None`. A method author cannot know which form a caller used, and the hosted console's upload grant produces exactly the `pipelex-storage://` form, so the fallback cannot be left to each method.

The normalizer therefore fills `public_url` for the two remaining forms, mirroring what `GeneratedContentFactory` already does for produced images (`pipelex/cogt/content_generation/generated_content_factory.py:181-205`):

- **A `pipelex-storage://` reference** gets a link signed through the storage provider, always, even when the input already carries a `public_url`. The reference is the durable fact and the link a derivative with an expiry, and the usual way an input arrives with both is a previous run's output passed back in, whose link may have expired.
- **An `http(s)` URL** gets `public_url = url` when the input carries none, since that URL is already the public one; a caller-supplied `public_url` is kept.

Signing a reference is no wider than reading it, which the operators consuming the input already do. On the hosted plane the platform refuses, before any run starts, a `pipelex-storage://` reference outside the caller's organization, so no link to another tenant's file can be minted this way.

A run with `is_normalize_data_urls_to_storage` off, or with mock inputs, skips normalization entirely and keeps today's behaviour; that switch governs the whole normalizer and this change does not widen it.

`DocumentContent` goes through the same function and gets the same treatment.

## What this does not fix

- **A report reopened after the link's lifespan.** A baked link still expires (`signed_urls_lifespan_seconds = 3600`, `pipelex/pipelex.toml:23`). Durable references in HTML markup and a renderer that resolves them are L-260918-4fd772 in this repo, with the rendering side in `mthds-form` and the console.
- **The webapp.** The item says a virtual-hosted link fixes a fresh render "on every surface"; it does not reach `app.pipelex.com`. The webapp's CSP allows images only from `'self'`, `data:` and `blob:` (`pipelex-app/src/lib/csp.ts:61`), and an HTML output renders in a `srcdoc` frame (`mthds-form/src/react/html-preview.tsx:214`), which inherits that policy, so an S3 image inside an HTML output is blocked there in either addressing form. The fix reaches the MCP console's views and every surface with no CSP: a saved HTML file, an email, a terminal.
- **Jinja's rendering of `None` as `None`.** Once every normalized input carries a `public_url`, the case stops arising for inputs, and a template author who wants a fallback writes one.

## Shipping and acceptance

The change ships as a `pipelex` release. The hosted plane runs it once the pins move: `pipelex-api` pins `pipelex`, and `pipelex-server` pins both `pipelex-api` (`api-hosted/pyproject.toml`) and `pipelex` itself (`temporal/pyproject.toml`, `daytona-sandbox/pyproject.toml`). Those moves ride the ordinary release train.

In this repo, acceptance is the unit test that presigns through real botocore and asserts the host, which a revert of the one-line style change turns red. On the hosted plane, acceptance is a fresh run of the catalog method "Fashion designer" on the dev console once the pins carry the release: every `<img src>` in its `inner_html` sits on `https://pipelex-app-dev.s3.us-west-2.amazonaws.com`, the moodboard's included, and claude.ai paints every picture. That check, and the stale comments, belong to the pipelex-mcp follow-up filed with this design.
