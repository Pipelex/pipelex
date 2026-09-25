---
status: landed
item: L-260925-94110e
---

# Plan: sign `public_url` virtual-hosted, and give every normalized input a `public_url`

The decisions and their evidence are in [`design.md`](design.md). One branch, one pull request, two phases with a checkpoint at the end. The work is test-first: each phase writes its failing tests, watches them fail for the right reason, then changes the code.

## Phase 1 — The S3 provider signs on the bucket's own host

Tests, in a new module `tests/unit/pipelex/tools/storage/test_s3_storage_provider_url_form.py` (the repo allows one test class per module), as a class that does not use the `mock_aioboto3` fixture, because the point is to exercise botocore's real addressing logic:

- [x] Presigning through a real aioboto3 session, with dummy credentials set through `monkeypatch` and `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` pointed at an empty file so the developer's own AWS configuration cannot leak in, yields a link whose host is `<bucket>.s3.<region>.amazonaws.com` and whose path is `/<key>`. Presigning makes no network call, so this stays a unit test.
- [x] The same presigning for a dotted bucket name yields the path-style link on `s3.<region>.amazonaws.com`.
- [x] For both kinds of bucket name, the signed link and the unsigned one (`signed_urls_lifespan=None`) name the same host and the same path.
- [x] Mutation check: remove the style from `_get_client_config` and watch the first test go red; restore the dotted-name branch of `_make_public_url` to the plain form and watch the third go red. Restore by editing, never with `git checkout`.

Code, in `pipelex/tools/storage/s3_storage_provider.py`:

- [x] `_get_client_config` adds `s3={"addressing_style": "virtual"}` to its `Config`, with a comment saying why the style is pinned: a CSP can name a bucket only by its own host, and botocore signs path-style whenever an endpoint is given.
- [x] `_make_public_url` builds the path-style regional form for a bucket name containing a dot and the virtual-hosted regional form otherwise, with a comment naming the wildcard certificate as the reason.
- [x] The existing mocked fixtures that fake a presigned link (`tests/unit/…/test_s3_storage_provider.py:38`, `tests/integration/pipelex/tools/storage/conftest.py:71`) already use the virtual-hosted regional form; confirm and leave them.

Documentation:

- [x] `docs/features/cloud-storage.md` says which URL form S3 links take, virtual-hosted on the bucket's regional host with the dotted-name exception, so an author writing a CSP knows the origin to allow.
- [x] `CHANGELOG.md` under Unreleased: the S3 provider signs and fetches on the bucket's own regional host instead of the shared regional endpoint, and a self-hosted deployment whose egress rules name only `s3.<region>.amazonaws.com` must allow `*.s3.<region>.amazonaws.com`.

Gates:

- [x] `make agent-check`, with the changes staged first so the drift digest sees them; handle any drift contract the storage files trigger with `make drift-plan` and `make drift-ack`.

## Phase 2 — Every normalized input carries a `public_url`

Tests, in a new module `tests/unit/pipelex/pipeline/test_input_normalizer_public_url.py` beside `test_input_normalizer.py` (one test class per module), with the storage provider mocked as that module already does:

- [x] An image input whose `url` is a `pipelex-storage://` reference comes out with the provider's signed link as `public_url` and its `url` unchanged.
- [x] The same input already carrying a `public_url` comes out with the freshly signed link instead.
- [x] An `http(s)` input with no `public_url` comes out with `public_url` equal to its `url`; one carrying a `public_url` keeps it.
- [x] A `DocumentContent` input gets the same treatment, one case for each form.
- [x] Update `test_well_formed_http_url_passes_through_unchanged` so it still asserts no network call and an unchanged `url`, and now asserts the filled `public_url`; do the same for `test_user_image_http_url_passthrough_when_fetch_disabled` in `tests/integration/pipelex/tools/storage/test_user_provided_image_storage.py`.
- [x] Mutation check: drop each new branch in turn and watch its test go red.

Code, in `pipelex/pipeline/input_normalizer.py`:

- [x] The `ResolvedHttpUrl` branch of `_normalize_url_content` returns a copy with `public_url = url` when the input has none, after the syntax check it already runs.
- [x] A `ResolvedPipelexStorage` branch replaces the pass-through at line 286: it signs through `storage.public_url(uri=content.url)` and returns a copy carrying the link.
- [x] The function's docstring and the pass-through comment say what each form now gets.

Knock-on checks:

- [x] Run the tests that pretty-print `TextAndImagesContent` and structured inputs. The premise turned out wrong for `TextAndImagesContent`: the normalizer never reaches its images (see the deferral below), so its rendering does not change; the structured-input and rendering tests passed unchanged.
- [x] Run the tests that snapshot a run's inputs or graph, since normalized inputs now carry one more field.

Documentation:

- [x] `docs/building-methods/concepts/native-concepts.md:79` and `:105` say the runtime fills `public_url` for every input it normalizes, a signed and therefore expiring link for a stored file and the URL itself for an `http(s)` one, and that a template baking it into HTML produces a report that stops loading once the link expires.
- [x] `CHANGELOG.md` under Unreleased: inputs given as a `pipelex-storage://` reference or an `http(s)` URL now carry a `public_url`, so a template writing `{{ image.public_url }}` no longer renders `None`.

## Checkpoint — ready for review

- [x] `make agent-check` clean.
- [x] `make agent-test` green.
- [x] `/rev`, at the depth `ledger review-profile` derives: round 1 at profile 3 (cubic, Codex review, the official code-review at `low`), then round 2 at the `defects` bar over round 1's fixes, both recorded on the item.
- [x] Record here what was decided during the build, any open question, and the last reviewed commit.

### Decisions taken during the build

- **Each new test class has its own module**, `test_s3_storage_provider_url_form.py` and `test_input_normalizer_public_url.py`, because the repo's test standard allows one test class per module.
- **A provider that cannot link a stored reference leaves the link the input carried.** In-memory storage returns no link at all; erasing a carried link the runtime cannot replace would lose information for nothing.
- **A reference the storage provider refuses as a key is an input error at normalization.** Signing now happens before the run, so the local provider's refusal of a path escaping its root surfaces there; it is raised as `PipelineInputContentError`, INPUT domain and not caller-facing, rather than as a bare storage error.
- **The unsigned S3 link uses botocore's own `check_dns_name`** instead of a hand-written dot test, so a legacy bucket name with uppercase letters or an underscore falls back to path-style exactly as the signed link does. Both unsigned builders, S3 and GCS, percent-encode the key as their signed forms do. Both came out of review round 1.
- **A NUL byte in a local input path or a local storage key is an input error.** `Path` rejects it with a bare `ValueError` rather than an `OSError`, so the local provider refuses such a key as `StorageInvalidUriError` and the normalizer's local-path branch catches `ValueError` beside `OSError`. The storage-reference branch made the first reachable before the run; the second predates this branch. Both came out of review round 2.
- **The public design describes the hosted plane's network and tenancy checks by role.** `pipelex` is a public repository, so the specifics sit on the ledger item instead, and the commit that added this design was rewritten before any pull request so that no commit carries them.

### Deferred

- **The normalizer does not reach the images inside a `TextAndImagesContent`**, nor those in a `PageContent`'s `text_and_images`: `_normalize_value` recurses only into `StructuredContent`, `ListContent` and lists, and `TextAndImagesContent` is a plain `StuffContent`. Their `data:` URLs are left unstored and their `public_url` unfilled. The gap predates this branch; review round 1 confirmed it, and the changelog and docs now say which placements are reached. Reaching them is a recursion branch in `_normalize_value` and its tests.
- **The storage configuration refuses a dotted bucket name**, for S3 and GCS alike, so the S3 provider's path-style fallback for one is reachable only by a provider constructed directly. Review round 2 proposed accepting dotted names; that is a feature choice, and one the shared GCS check would need too, so the docs and changelog now say the configuration refuses them, and the fallback stays as a defensive measure.
- **The design still names a few paths inside internal repositories**: the webapp's CSP source file and the hosted plane's member manifests. Review round 2 raised it; nothing named is secret, and rewording them by role is hygiene rather than a defect at that round's bar.

### Last reviewed commit

Round 1 reviewed the branch at the commit titled "Mark the campaign active and tick the built phases", and round 2 at the commit titled "Unsigned storage links encode their key and match botocore's host rule", each before its round's fixes.

## After the merge

The branch merged into `dev` as #1260, squash commit `4f535ec56`, and `/ledger-land` closed the item on that merge; the change reaches `main` with the next pipelex release. The hosted acceptance, a fresh "Fashion designer" run on the dev console painting every picture from the bucket's regional host, waits for the release train to carry the change into `pipelex-api` and `pipelex-server`, and is recorded on the pipelex-mcp follow-up along with the comments there that still call the runtime's link path-style.
