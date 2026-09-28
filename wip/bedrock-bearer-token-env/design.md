---
status: draft
item: L-260927-06f4db
---

# The configured Bedrock access variant wins over `AWS_BEARER_TOKEN_BEDROCK`

## The bug, verified

With `[runtime.aws] bedrock_access_variant = "aws_access"`, which is the shipped default in `pipelex/pipelex.toml`, `AnthropicFactory.make_anthropic_client` builds `AsyncAnthropicBedrock(aws_access_key=…, aws_secret_key=…, aws_region=…)` and passes no `api_key`. The anthropic SDK's Bedrock client then fills `api_key` from `AWS_BEARER_TOKEN_BEDROCK` and refuses the combination with explicit credentials:

```
ValueError Cannot specify both `api_key` and AWS credentials (`aws_access_key`, `aws_secret_key`, `aws_session_token`, `aws_profile`)
```

Reproduced offline against anthropic 0.99.0 with `AWS_BEARER_TOKEN_BEDROCK=dummy`: the constructor raises exactly that, and the same construction without the variable succeeds. The lookup is unconditional in the SDK (`if api_key is None: api_key = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")`, in both the sync and async clients), and it is unchanged on the SDK's `main` at 1.8.0, so no upgrade fixes it. Passing an empty string does not help either: `""` is not `None`, so it skips the lookup and then trips the same refusal.

The raw `ValueError` escapes pipelex's error model at client construction, for every `bedrock_anthropic` model. The variable is not exotic: it is the standard name for a Bedrock API key, which AWS tooling and Claude Code on Bedrock read, so a developer who configured one of those in a shell profile cannot run a single `bedrock_anthropic` model under pipelex's default configuration.

## Where else the variable reaches

- **`bedrock_anthropic` under `bedrock_token`** has no clash. Pipelex reads the token itself, from `AWS_BEARER_TOKEN_BEDROCK` under `api_key_method = "env"` or from the secrets provider under `"secret_provider"`, and passes it as `api_key` with no AWS credentials.
- **The native Bedrock clients** (`bedrock_aioboto3`, renamed `bedrock_aiobotocore` by L-260927-61a69f, and `bedrock_boto3`) never read `[runtime.aws]` at all, and botocore prefers bearer auth for the `bedrock` signing name whenever the variable is set and no signature version is set in code — explicit access keys do not count. An offline probe capturing the `Authorization` header on a `converse` call shows `Bearer dummy` both with the default chain and with explicit keys, and SigV4 only once `Config(signature_version="v4")` is set. That path fails silently rather than loudly, and deciding it needs a question this item does not have to answer (whether to give up boto's default credential chain), so it is filed as its own bug, L-260928-bfd13b, blocked on the aiobotocore swap that renames its files.

## Decision: the configured variant wins

The item allows two outcomes: turn the clash into a configuration error, or decide which one wins and say so. **Pipelex's `bedrock_access_variant` wins.** Under `aws_access`, a `bedrock_anthropic` client signs every request with SigV4 from the credentials `[runtime.aws]` sourced, and an `AWS_BEARER_TOKEN_BEDROCK` in the environment is ignored.

Why this rather than a refusal:

- **`[runtime.aws]` is pipelex's one statement of where Bedrock credentials come from.** Under `api_key_method = "secret_provider"` the user chose the secrets provider precisely so that ambient environment variables would not matter; an SDK lookup that bypasses it contradicts that choice, and refusing on it would make the contradiction pipelex's own rule.
- **A refusal punishes the common case.** The variable is typically set for a different tool, the variant is the default rather than something the user typed, and the remedy a refusal would ask for — removing a variable from the process environment for pipelex alone — is awkward in a shell and impossible from a `.env` file, since an empty value still clashes.
- **Letting the configured variant win has no harmful outcome.** Either the access keys are there and the call works with them, or they are missing and pipelex already raises `AwsCredentialsError` — which this change extends to say that a bearer token is present and how to use it. Nothing ever runs on credentials the user did not configure.

Rejected alternatives:

- **A configuration error naming both.** Sound, and the cheapest to build, but it blocks the common case for the reasons above. It remains the fallback if the mechanism below proves unmaintainable against a future SDK.
- **Masking the variable while the client is constructed.** `os.environ` is process-global, so any other thread reading it during construction sees it disappear; and `with_options` re-runs the constructor later, re-reading the variable, so the mask would have to be repeated at every copy.
- **Only translating the `ValueError` into a pipelex error.** That is the refusal with extra steps, and it keys on an SDK message string.

## Mechanism

A small subclass of `AsyncAnthropicBedrock` in `pipelex/providers/anthropic/`, used only for the `aws_access` branch. Its constructor passes the SDK nothing but the region and the transport options, which never clashes, then sets `api_key` to `None` and assigns the AWS credentials. The SDK's request hook signs with SigV4 whenever `api_key` is `None`, reading exactly those attributes. The subclass is still an `AsyncAnthropicBedrock`, so the worker's `isinstance` check and `instructor.from_anthropic` accept it unchanged.

`with_options` (the SDK's `copy`) rebuilds the client through `self.__class__(…)` with the stored credentials and `api_key=None`, so a copy takes the same path. An offline probe confirmed it: a client built this way and its `with_options` copy both sent `AWS4-HMAC-SHA256 Credential=<key id>/…` with `AWS_BEARER_TOKEN_BEDROCK` set. The probe also showed that the SDK's `copy` does not carry a custom `http_client` over unless one is passed again, which matters to the tests, not to production.

The constructor refuses a non-`None` `api_key`: the class exists to sign with SigV4, and a caller handing it a token wants the other variant.

The cost is coupling to four public attributes of the SDK client (`api_key`, `aws_access_key`, `aws_secret_key`, `aws_session_token`) and to the rule that `api_key is None` means SigV4. The guard is a behavioural test on the wire, not on the attributes: a request sent through an `httpx.MockTransport` with the variable set must carry a SigV4 `Authorization` header naming the configured key id. An SDK release that changes either the attributes or the rule turns that test red at the dependency bump.

## What the user sees

- **The docs say which wins.** `docs/configuration/config-technical/aws-config.md` gains a section on `bedrock_access_variant`: what each variant reads (it documents neither today, and its sample shows `bedrock_token` although `aws_access` is the default), that under `aws_access` pipelex signs `bedrock_anthropic` requests with the configured keys and ignores `AWS_BEARER_TOKEN_BEDROCK`, and that the native Bedrock clients currently follow boto's own credential chain, in which that variable wins — stated as today's behaviour, pointing at nothing volatile.
- **The missing-keys error points at the token.** When `aws_access` cannot find its keys and `AWS_BEARER_TOKEN_BEDROCK` is set, the `AwsCredentialsError` raised for a `bedrock_anthropic` client adds that the environment carries a Bedrock bearer token and that `bedrock_access_variant = "bedrock_token"` uses it. That is the one situation where a user plausibly meant the token.
- **A verbose log line** records, when the variable is set under `aws_access`, that it is being ignored. Not a warning: the outcome is never harmful, and a developer who keeps the variable for another tool would otherwise read the same warning on every run.

## Noticed, not in scope

Three neighbouring gaps turned up while reading this code. None is the clash, and each would change behaviour someone may rely on, so they are recorded here rather than folded in:

- **`bedrock_token` passes no region.** The SDK then infers one from `AWS_REGION`, the boto profile, or `us-east-1`, so under `api_key_method = "secret_provider"` a region stored with the secrets is ignored.
- **`aws_access` passes no session token.** `get_aws_access_keys` reads neither `AWS_SESSION_TOKEN` nor its secret, so temporary STS credentials cannot sign a `bedrock_anthropic` request.
- **The SDK's `copy` drops `aws_profile`.** Upstream, and harmless to pipelex, which never passes a profile.
