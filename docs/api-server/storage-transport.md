# Storage transport: reading back what a run stores

A run hands back large values by reference. A `Text`, `Markdown`, `Html` or `JSON` value past `[runtime.storage] inline_text_max_bytes` (4096 bytes by default), an image a run generates and a file it receives are kept in the server's configured storage and travel in the answer as `pipelex-storage://` references. Every client reads one back the same way, whichever server it talks to: it sends the references to `POST /v1/resolve-storage-url/bulk`, receives one short-lived link per reference, and fetches each link without its credential. Both SDKs' `load_stored_texts` / `loadStoredTexts` and `download_artifacts` / `downloadArtifacts` work this way.

On the hosted platform the route belongs to the platform, which checks that the caller's organization owns each object and answers presigned object-store links. This server, run on its own, serves the same contract for its own storage, so neither SDK nor any client built on them has to know which kind of server it talks to.

## `POST /v1/resolve-storage-url/bulk`

The request is `{"uris": [...]}`, at most 100 references, each at most 512 characters, with no other field. More references, a longer one or an unknown field is a `422` `request.invalid`, and a client with more references sends them in chunks, as both SDKs do.

The answer is `{"items": [...]}`, one item per reference in the request's order, each `{"uri", "url", "expires_at", "content_type", "error"}`, the platform's shape field for field. A resolved reference carries its link in `url`, the link's expiry in `expires_at`, and the content type its extension implies in `content_type`, with `error` null. A refused reference carries `error`, a problem item `{"code", "detail", "params"}`, with the three link fields null. The request is a `200` whenever every reference got a verdict, so a client branches on each item's `error`, never on the status:

- A reference that does not parse is refused as `pipelex.storage.uri_invalid`: it does not start with `pipelex-storage://`, its key has fewer than two segments, a segment is empty, `.` or `..`, or the key holds a backslash or a control character.
- A reference outside the caller's scope is refused as `auth.forbidden` whose `params.requirement` is `read_scope_under_caller`, the requirement this server's other scope refusals name.

The route sits behind the deployment's authentication like every other `/v1` route, and a caller resolves only references under its own scope, the scope its runs write under by default and its hash entries resolve in. On a deployment that identifies no caller, `AUTH_MODE=none` without forwarded identity or the shared `AUTH_MODE=api_key`, that scope is `single-tenant`, the one tenant such a deployment has. Under `AUTH_MODE=jwt` it is the caller's own `user_id`, so a caller reads back what its own runs stored and nothing another caller's runs stored. A run that sent its own `storage_scope` outside that scope stores where no caller of this route can resolve.

Resolving checks only that the caller may read the reference, never that a file is stored there, as a presigned URL does not either: a link to an address nothing was stored at answers a `404` when it is fetched.

## `GET /v1/storage/{key}`

Each resolved `url` is this server's own download route, the reference's key in its path, percent-encoded segment by segment, and a query holding an expiry and an HMAC-SHA256 signature over the key and the expiry. The signed query is the link's authorization, so the route needs no bearer token, which is what lets a browser display an image or a document straight from it. Only a caller who passed the deployment's authentication on the resolve route, for a reference under its own scope, holds a link, for `STORAGE_LINK_TTL_SECONDS` (fifteen minutes by default).

The answer is the object's bytes under the content type stored with them, else the one their name implies, sandboxed (`Content-Security-Policy: sandbox`, `X-Content-Type-Options: nosniff`) so that a stored HTML page never runs a script on the server's origin. A missing, malformed, forged or expired signature is a `403` `auth.forbidden` whose `params.requirement` is `signed_storage_link`, and a link whose address holds no file a `404` `pipelex.storage.object_missing`.

A link starts with `PUBLIC_BASE_URL` when the deployment sets it, the address its clients reach the API at, so a server behind a proxy that terminates TLS or adds a path prefix hands out links on its public origin; unset, a link starts with the URL the resolve request arrived at. Links are signed with `LINK_SIGNING_KEY`, the key the upload targets of `POST /v1/blobs/missing` are signed with too, each kind of link under a purpose of its own so that neither signature holds for the other. Unset, each process draws its own key, so a link stops holding when the process restarts, and a deployment serving one API through several instances must set it, the same on every instance. See [Configuration](configuration.md).

Every link goes through this server, whichever storage backend it is configured with, S3 and GCP included, so there is one code path and one access rule.

## Behind a trusted proxy

When the server trusts forwarded identity (`AUTH_MODE=none` with `TRUST_FORWARDED_IDENTITY_HEADERS=true`), it sits behind a host that owns tenancy, as on the hosted plane, and neither route is mounted: a request for either is a `404` `request.not_found`. The forwarded id is a user, not the organization that owns what the runner stores, so only the host can decide who may read an object. The hosted edge sends `/v1/resolve-storage-url*` to its platform, and not mounting the route here keeps a misrouted request from reaching a reader that cannot check organizations.

## What is not served

`POST /v1/upload` and the single `POST /v1/resolve-storage-url` were removed from this server when storage moved to the hosted platform, and only the bulk route came back, since no client the SDKs ship calls the single one. They used to key objects under the caller's own id and authorize a read by comparing that first segment with the requester, an ownership model with no notion of a team: on the hosted side those references were saved onto organization-scoped rows, so the second member of a team to open a shared method was refused their own team's file. The hosted platform still serves both, at `api.pipelex.com`, keyed by organization.

To give a self-hosted run a file, pass a public HTTP(S) URL or a base64 data URL directly as a `Document` or `Image` `url`, or send the method's own files by hash through `POST /v1/blobs/missing` ([Sending files by hash](pipe-run.md#sending-files-by-hash)).
