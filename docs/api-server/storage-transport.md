# Storage transport (`/upload`, `/resolve-storage-url`) — REMOVED

**Both routes are gone from this server.** They were never part of the published Pipelex API contract — neither the MTHDS Protocol nor the build extensions — and their docstrings said so. The "Future ownership" section this page used to carry predicted the move; it has happened, and the removal decision it left open was taken with it.

## Where they went

To the hosted Pipelex platform, still at `POST /v1/upload` and `POST /v1/resolve-storage-url` on `api.pipelex.com`, with byte-identical request and response shapes. Released SDK versions keep working: `@pipelex/sdk`'s `uploadFile` / `prepareInputs` and `pipelex-sdk`'s `upload_file` / `prepare_inputs` are unchanged, and the `pipelex-storage://` scheme is unchanged.

## Why they could not stay here

Both keyed S3 objects under the caller's own id — `{user_id}/assets/{uuid}.{ext}` — and authorized a read by comparing that first path segment against the requester. That is an ownership model with no notion of a team, and on the hosted side those URIs get saved onto **organization-scoped** rows, so the second member of a team to open a shared method got a `403` on their own team's file.

Fixing it means putting the organization at segment 0, and this server has no organization concept to put there. It is a generic execution engine: a single opaque caller id is its entire trusted identity surface, by design. So the routes belong where membership is already resolved before the request arrives.

## What a self-hoster does now

Nothing in the runtime changed — only the two HTTP routes are gone. The storage *provider* is untouched: `get_storage_provider()`, `pipelex-storage://` URIs, and everything the runtime does with them work exactly as before, and a pipeline still reads and writes assets through the configured backend.

What a self-hosted deployment no longer gets is an HTTP surface for putting bytes in and getting them back out. If you need one, it is yours to build, and its authorization model is yours to choose — which is the honest outcome, since the one removed here only ever fit a single-user deployment.

You can also skip storage entirely for most inputs: pass a public HTTP(S) URL or a base64 data URL directly as a `Document` / `Image` `url`.
