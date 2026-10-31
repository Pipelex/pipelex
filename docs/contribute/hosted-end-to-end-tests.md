---
title: "Hosted End-to-End Tests"
description: "How pipelex's hosted end-to-end tests get their Pipelex API key, check the account it acts for before the first case, and refuse production by default."
---

# Hosted End-to-End Tests

`tests/e2e/pipelex/cli/test_hosted_run_cli.py` spawns the real `pipelex` and `pipelex-agent` binaries against a live hosted Pipelex API: it runs published methods on it by flag and by configured default, uploads a local input file, and checks that `--base-url` wins over `PIPELEX_BASE_URL`. Every case spends hosted credit, so the module carries the `pipelex_api` marker, which keeps it out of `make agent-test`, out of CI and out of the default pytest selection. It is selected with `-m pipelex_api` (`make test-pipelex-api` runs every test that carries the marker), and it is skipped when `PIPELEX_API_KEY` is unset.

## Where its account comes from

The cases act as one test account, so that what they spend and leave behind lands in an organization kept for them. The Pipelex team runs them as its QA Builder account in its QA Runtime organization on the dev plane, whose key its `test-account run` command hands over:

```bash
test-account run pipelex-hosted-e2e -- .venv/bin/pytest -m pipelex_api tests/e2e/pipelex/cli/test_hosted_run_cli.py
```

The command checks the account first, then runs the tests with:

- `PIPELEX_API_KEY`, the account's key in that organization;
- `PIPELEX_BASE_URL`, the dev plane's origin;
- the key's expectations, `PIPELEX_API_KEY_EXPECTED_ORG_ID`, `PIPELEX_API_KEY_EXPECTED_ROLE` and `PIPELEX_API_KEY_EXPECTED_EMAIL`: the organization's id, the account's role there and its email, as `GET /v1/me` should state them;
- `DO_NOT_TRACK=1`, so nothing the tests start reports anonymous usage statistics.

Anyone else exports the same variables for an account of their own, its expectations being what `GET /v1/me` states for its key, and sets `DO_NOT_TRACK=1`:

```bash
export PIPELEX_API_KEY=<the key>
export PIPELEX_BASE_URL=<the API origin, such as https://api.pipelex.com>
export PIPELEX_API_KEY_EXPECTED_ORG_ID=<organization.org_id>
export PIPELEX_API_KEY_EXPECTED_ROLE=<organization.role_in_org>
export PIPELEX_API_KEY_EXPECTED_EMAIL=<email>
export DO_NOT_TRACK=1
.venv/bin/pytest -m pipelex_api tests/e2e/pipelex/cli/test_hosted_run_cli.py
```

Each case then runs its subprocess in a hermetic home, with an environment built from nothing but that key, that origin and no provider key, so the developer's own `~/.pipelex` is never read.

## What it checks before the first case

Before the first case, `require_hosted_account` (`tests/helpers/hosted_account_check.py`) checks, in this order:

1. **That no variable it reads came from a `.env` file.** pipelex loads `~/.pipelex/.env` (or the one in `PIPELEX_HOME`) and then the working directory's `.env` over the environment it was started with, so a key saved by `pipelex login` would silently replace the one handed over. The check asks `pipelex.system.environment.get_dotenv_source` about `PIPELEX_API_KEY`, `PIPELEX_BASE_URL`, the three expectations and `PIPELEX_HOSTED_E2E_ALLOW_PRODUCTION`, and names the file that set each one that was replaced.
2. **That the origin is not the production API.** Without `PIPELEX_BASE_URL` the runs would go to `https://api.pipelex.com`, so an unset origin and one on that host are refused unless `PIPELEX_HOSTED_E2E_ALLOW_PRODUCTION=1` asks for production on purpose.
3. **That the key's three expectations are set.** A run without them is refused, its message naming `test-account run`.
4. **That `GET /v1/me`, asked with the key, states what they expect**: `organization.org_id` equal to `PIPELEX_API_KEY_EXPECTED_ORG_ID`, `organization.role_in_org` equal to `PIPELEX_API_KEY_EXPECTED_ROLE`, and `email` equal to `PIPELEX_API_KEY_EXPECTED_EMAIL` ignoring case.

Nothing is sent before the first three hold. Any finding stops the whole session once, with every finding, each naming the variable, the value found and the value expected. A platform whose `/v1/me` answers without the `organization` member is reported as "the platform does not state the key's organization yet" and stops the session too: it is never a pass. An account, organization or role that differs from what the expectations say is restored by the owner of the test-account registry the expectations come from, never by a test: the cases do not change who the key belongs to.

## Fixtures

The cases need no fixture of their own in the organization: the methods are the public `github.com/Pipelex/methods` packages at a pinned tag, which the hosted API fetches itself, and the one input file is uploaded by the run that uses it.
