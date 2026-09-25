---
status: draft
item: L-260925-94110e
---

# Plan: sign `public_url` virtual-hosted, and give every normalized input a `public_url`

The decisions and their evidence are in [`design.md`](design.md). One branch, one pull request, two phases with a checkpoint at the end. The work is test-first: each phase writes its failing tests, watches them fail for the right reason, then changes the code.

## Phase 1 — The S3 provider signs on the bucket's own host

Tests, in `tests/unit/pipelex/tools/storage/test_s3_storage_provider.py`, as a new class that does not use the `mock_aioboto3` fixture, because the point is to exercise botocore's real addressing logic:

- [ ] Presigning through a real aioboto3 session, with dummy credentials set through `monkeypatch` and `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` pointed at an empty file so the developer's own AWS configuration cannot leak in, yields a link whose host is `<bucket>.s3.<region>.amazonaws.com` and whose path is `/<key>`. Presigning makes no network call, so this stays a unit test.
- [ ] The same presigning for a dotted bucket name yields the path-style link on `s3.<region>.amazonaws.com`.
- [ ] For both kinds of bucket name, the signed link and the unsigned one (`signed_urls_lifespan=None`) name the same host and the same path.
- [ ] Mutation check: remove the style from `_get_client_config` and watch the first test go red; restore the dotted-name branch of `_make_public_url` to the plain form and watch the third go red. Restore by editing, never with `git checkout`.

Code, in `pipelex/tools/storage/s3_storage_provider.py`:

- [ ] `_get_client_config` adds `s3={"addressing_style": "virtual"}` to its `Config`, with a comment saying why the style is pinned: a CSP can name a bucket only by its own host, and botocore signs path-style whenever an endpoint is given.
- [ ] `_make_public_url` builds the path-style regional form for a bucket name containing a dot and the virtual-hosted regional form otherwise, with a comment naming the wildcard certificate as the reason.
- [ ] The existing mocked fixtures that fake a presigned link (`tests/unit/…/test_s3_storage_provider.py:38`, `tests/integration/pipelex/tools/storage/conftest.py:71`) already use the virtual-hosted regional form; confirm and leave them.

Documentation:

- [ ] `docs/features/cloud-storage.md` says which URL form S3 links take, virtual-hosted on the bucket's regional host with the dotted-name exception, so an author writing a CSP knows the origin to allow.
- [ ] `CHANGELOG.md` under Unreleased: the S3 provider signs and fetches on the bucket's own regional host instead of the shared regional endpoint, and a self-hosted deployment whose egress rules name only `s3.<region>.amazonaws.com` must allow `*.s3.<region>.amazonaws.com`.

Gates:

- [ ] `make agent-check`, with the changes staged first so the drift digest sees them; handle any drift contract the storage files trigger with `make drift-plan` and `make drift-ack`.

## Phase 2 — Every normalized input carries a `public_url`

Tests, in `tests/unit/pipelex/pipeline/test_input_normalizer.py`, with the storage provider mocked as the module already does:

- [ ] An image input whose `url` is a `pipelex-storage://` reference comes out with the provider's signed link as `public_url` and its `url` unchanged.
- [ ] The same input already carrying a `public_url` comes out with the freshly signed link instead.
- [ ] An `http(s)` input with no `public_url` comes out with `public_url` equal to its `url`; one carrying a `public_url` keeps it.
- [ ] A `DocumentContent` input gets the same treatment, one case for each form.
- [ ] Update `test_well_formed_http_url_passes_through_unchanged` so it still asserts no network call and an unchanged `url`, and now asserts the filled `public_url`; do the same for `test_user_image_http_url_passthrough_when_fetch_disabled` in `tests/integration/pipelex/tools/storage/test_user_provided_image_storage.py`.
- [ ] Mutation check: drop each new branch in turn and watch its test go red.

Code, in `pipelex/pipeline/input_normalizer.py`:

- [ ] The `ResolvedHttpUrl` branch of `_normalize_url_content` returns a copy with `public_url = url` when the input has none, after the syntax check it already runs.
- [ ] A `ResolvedPipelexStorage` branch replaces the pass-through at line 286: it signs through `storage.public_url(uri=content.url)` and returns a copy carrying the link.
- [ ] The function's docstring and the pass-through comment say what each form now gets.

Knock-on checks:

- [ ] Run the tests that pretty-print `TextAndImagesContent` and structured inputs: an `http(s)` image now has a `public_url`, which adds the "Display" column to the rich table (`pipelex/core/stuffs/text_and_images_content.py:115`). Update expectations that pinned the old rendering, and read each diff rather than accepting it wholesale.
- [ ] Run the tests that snapshot a run's inputs or graph, since normalized inputs now carry one more field.

Documentation:

- [ ] `docs/building-methods/concepts/native-concepts.md:79` and `:105` say the runtime fills `public_url` for every input it normalizes, a signed and therefore expiring link for a stored file and the URL itself for an `http(s)` one, and that a template baking it into HTML produces a report that stops loading once the link expires.
- [ ] `CHANGELOG.md` under Unreleased: inputs given as a `pipelex-storage://` reference or an `http(s)` URL now carry a `public_url`, so a template writing `{{ image.public_url }}` no longer renders `None`.

## Checkpoint — ready for review

- [ ] `make agent-check` clean.
- [ ] `make agent-test` green.
- [ ] `/rev`, at the depth `ledger review-profile` derives.
- [ ] Record here what was decided during the build, any open question, and the SHA of the last reviewed commit, so the pull request can be opened from a fresh session.

## After the merge

`/ledger-land` closes this item on the merge. The hosted acceptance, a fresh "Fashion designer" run on the dev console painting every picture from the bucket's regional host, waits for the release train to carry the change into `pipelex-api` and `pipelex-server`, and is recorded on the pipelex-mcp follow-up along with the comments there that still call the runtime's link path-style.
