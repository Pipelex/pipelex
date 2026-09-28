---
status: active
item: L-260927-06f4db
---

# Plan: the configured Bedrock access variant wins over `AWS_BEARER_TOKEN_BEDROCK`

The decisions and their rationale are in [`design.md`](design.md). One phase, on `fix/Bedrock-bearer-token-env` from `dev`. It touches only `pipelex/providers/anthropic/`, the docs and the changelog, none of which the in-flight `chore/Bumping` branch (L-260927-56ef15, L-260927-61a69f) changes, so it does not wait for that branch. The native Bedrock path is L-260928-bfd13b and is not part of this plan.

## Tests first

A new `tests/unit/pipelex/providers/anthropic/test_anthropic_bedrock_auth.py`, offline, with a module docstring stating the rule it pins: under `aws_access` the configured keys sign, whatever the environment says. `get_config` is patched as in `test_anthropic_client_auth.py`, with `runtime.aws` a real `AwsConfig` and the variables set through `monkeypatch.setenv`.

- [x] **The wire carries SigV4 with the variable set.** The SigV4 client, given an `httpx.AsyncClient` over an `httpx.MockTransport`, sends a `messages.create` whose `Authorization` header starts with `AWS4-HMAC-SHA256 Credential=<the configured key id>/` and never with `Bearer`.
- [x] **A `with_options` copy signs the same way**, the mock transport passed again, since the SDK's `copy` does not carry a custom `http_client` over.
- [x] **The factory builds that client under `aws_access`**, with the variable set and with it unset: it returns the SigV4 subclass, `api_key` is `None`, and the region and key id are the configured ones. This is the test that fails today with the `ValueError`.
- [x] **`bedrock_token` is unchanged**: the factory passes the token as `api_key`, and a request carries `Bearer <token>`.
- [x] **Missing keys with the token present** raise `AwsCredentialsError` whose message names `AWS_BEARER_TOKEN_BEDROCK` and `bedrock_token`; with the token absent, the message carries no such hint.
- [x] **The subclass refuses a non-`None` `api_key`.**

## Implementation

- [x] `pipelex/providers/anthropic/anthropic_bedrock_sigv4.py`: the `AsyncAnthropicBedrock` subclass. Its constructor takes the credentials and the region as keywords, passes the SDK the region and the remaining options only, then sets `api_key = None` and the three credential attributes. Its docstring carries the why: the SDK's unconditional lookup, and the wire test that guards the coupling.
- [x] `AnthropicFactory.make_anthropic_client`, `aws_access` branch: build the subclass; log at verbose level when `AWS_BEARER_TOKEN_BEDROCK` is set and ignored; when `get_aws_access_keys` raises `AwsCredentialsError` and the variable is set, re-raise it `from` the original with the hint appended. The environment is read through `pipelex.system.environment`, and the variable's name through `BEDROCK_TOKEN_VAR_NAME` in `pipelex/tools/aws/aws_config.py`, never a new literal.
- [x] Mutation-check the tests: drop the `api_key = None` assignment and watch the wire test go red; restore by re-applying the edit, never with `git checkout`. Dropping it turned the two wire tests and the factory test with the token set red; the factory's missing-keys hint was seen red before it existed.

## Docs and changelog

- [x] `docs/configuration/config-technical/aws-config.md`: a `bedrock_access_variant` section covering both variants, the variables each reads, which one wins under `aws_access` for `bedrock_anthropic`, and how the native Bedrock clients behave today. Correct the sample so it shows the default `aws_access` and names the alternative. MkDocs rules: a blank line before every list.
- [x] `CHANGELOG.md`, `[Unreleased]` under `### Fixed`: one bold-labelled entry saying that `bedrock_anthropic` models under `aws_access` sign with the configured keys when `AWS_BEARER_TOKEN_BEDROCK` is set, where they used to fail at client construction with a raw `ValueError`.

## Checkpoint: ready for review

- [x] `make agent-check`, with the changes staged first since the drift digest reads the index; handle any drift contract the anthropic or docs change opens.
- [x] `make agent-test`.
- [ ] Optional live check, paid, only on the user's go-ahead: `TestLLMGenText` on `claude-4.5-haiku` via `bedrock` with `AWS_BEARER_TOKEN_BEDROCK` set, which failed all its cases in the evidence run. Not run under the goal that executed this plan, which gave no go-ahead for paid inference; the offline wire tests stand in for it.
- [ ] `/rev`.
- [ ] PR `fix/Bedrock-bearer-token-env · L-260927-06f4db`, body ending `Closes L-260927-06f4db`; this document and `design.md` flip to `active` when the plan is ratified, and `/ledger-land` flips them to `landed`.
