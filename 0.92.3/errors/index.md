# Error Codes

An error code names a situation a runner or a client can meet, and its type URI is the URL of the code's page. A code of the MTHDS standard, such as `input.missing`, is a core code, documented with the standard on [mthds.ai](https://mthds.ai/latest/errors/) at `https://mthds.ai/errors/<code>`. A code that starts with `pipelex.` names a situation the standard leaves to its implementations, and has its page here, at `https://docs.pipelex.com/errors/<code>`. Each page says what its code means, who must act and what to do, and gives the code's steps, parameters and templates.

These pages are generated from the Pipelex error registry, which follows the [MTHDS error registry format](https://mthds.ai/latest/spec/error-registry/) under the `pipelex` prefix the core registry registers to Pipelex. The registry is published with every Pipelex release, as the release asset `pipelex-error-registry.json` on [GitHub](https://github.com/Pipelex/pipelex/releases) and inside the `pipelex` package. This is version `0.92.3` of the registry. [The Error Registry](../contribute/error-registry.md) describes how it is maintained.

Every Pipelex error carries a code, one of these or a core code: its problem document names it as `code`, and its `type` is the code's page. The [Error Model](../under-the-hood/error-model.md#error-codes-and-the-pipelex-error-registry) describes how an error class declares the code it raises.

## pipelex.billing { #pipelex-billing }

Credit and subscriptions: what an organization's plan and balance allow.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.billing.plan_limit`](pipelex/billing/plan_limit.md) | The account's plan does not allow this | `account` | `no` | `409` |
| [`pipelex.billing.credit_exhausted`](pipelex/billing/credit_exhausted.md) | The organization is out of credit | `account` | `no` | `402` |
| [`pipelex.billing.subscription_conflict`](pipelex/billing/subscription_conflict.md) | The subscription's state does not allow this | `account` | `no` | `409` |
| [`pipelex.billing.plan_refused`](pipelex/billing/plan_refused.md) | The plan's rules refuse this change | `input` | `no` | `409` |

## pipelex.org { #pipelex-org }

Organizations, their members, their API keys and their promo codes.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.org.required`](pipelex/org/required.md) | An organization is required | `account` | `no` | `403` |
| [`pipelex.org.mismatch`](pipelex/org/mismatch.md) | The reference belongs to another organization | `input` | `no` | `403` |
| [`pipelex.org.not_found`](pipelex/org/not_found.md) | The organization's resource does not exist | `input` | `no` | `404` |
| [`pipelex.org.not_manageable`](pipelex/org/not_manageable.md) | The resource cannot be changed this way in its state | `input` | `no` | `409` |
| [`pipelex.org.already_exists`](pipelex/org/already_exists.md) | The organization's resource already exists | `input` | `no` | `409` |
| [`pipelex.org.promo_invalid`](pipelex/org/promo_invalid.md) | The promo code cannot be redeemed | `input` | `no` | `422` |
| [`pipelex.org.promo_credit_pending`](pipelex/org/promo_credit_pending.md) | The promo credit is pending | `runtime` | `no` | `502` |

## pipelex.catalog { #pipelex-catalog }

Saved methods in an organization's catalog.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.catalog.not_found`](pipelex/catalog/not_found.md) | The saved method does not exist | `input` | `no` | `404` |
| [`pipelex.catalog.not_published`](pipelex/catalog/not_published.md) | The saved method has no published version | `input` | `no` | `409` |
| [`pipelex.catalog.being_deleted`](pipelex/catalog/being_deleted.md) | The saved method is being deleted | `input` | `no` | `409` |
| [`pipelex.catalog.deletion_failed`](pipelex/catalog/deletion_failed.md) | The saved method's deletion failed | `runtime` | `yes` | `503` |
| [`pipelex.catalog.update_conflict`](pipelex/catalog/update_conflict.md) | The saved method changed since it was read | `input` | `no` | `409` |
| [`pipelex.catalog.selector_invalid`](pipelex/catalog/selector_invalid.md) | The catalog selector is malformed | `input` | `no` | `422` |
| [`pipelex.catalog.link_conflict`](pipelex/catalog/link_conflict.md) | The directory is linked to another method | `input` | `no` | none (client) |

## pipelex.run { #pipelex-run }

Pipelex's extensions to runs.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.run.already_exists`](pipelex/run/already_exists.md) | A run with this id already exists | `input` | `no` | `409` |

## pipelex.request { #pipelex-request }

Refusals of a request's shape that name a fact no core code carries.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.request.dependency_key_mismatch`](pipelex/request/dependency_key_mismatch.md) | A dependency is keyed by another address than its manifest declares | `input` | `no` | `422` |

## pipelex.storage { #pipelex-storage }

Pipelex's storage addresses and uploads.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.storage.uri_invalid`](pipelex/storage/uri_invalid.md) | The storage address is malformed | `input` | `no` | `422` |
| [`pipelex.storage.not_found`](pipelex/storage/not_found.md) | A stored file is gone | `runtime` | `no` | `500` |
| [`pipelex.storage.damaged`](pipelex/storage/damaged.md) | A stored file is damaged | `runtime` | `no` | `500` |
| [`pipelex.storage.unavailable`](pipelex/storage/unavailable.md) | Storage is unavailable | `runtime` | `yes` | `503` |
| [`pipelex.storage.not_configured`](pipelex/storage/not_configured.md) | This deployment serves no storage for that address | `operator` | `no` | `500` |
| [`pipelex.storage.grant_unusable`](pipelex/storage/grant_unusable.md) | The upload grant is spent or expired | `runtime` | `yes` | `403` |
| [`pipelex.storage.grant_mismatch`](pipelex/storage/grant_mismatch.md) | The upload differs from its grant | `runtime` | `no` | `403` |
| [`pipelex.storage.upload_refused`](pipelex/storage/upload_refused.md) | Storage refused the upload | `runtime` | `no` | `403` |

## pipelex.security { #pipelex-security }

Pipelex's own refusals made for safety, each recorded as a security event.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.security.reserved_key`](pipelex/security/reserved_key.md) | The request carries a reserved key | `input` | `no` | `422` |
| [`pipelex.security.result_outside_scope`](pipelex/security/result_outside_scope.md) | A result location lies outside the run | `runtime` | `no` | `500` |

## pipelex.config { #pipelex-config }

The runtime's own configuration.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.config.invalid`](pipelex/config/invalid.md) | The runtime's configuration is invalid | `operator` | `no` | `500` |
| [`pipelex.config.syntax`](pipelex/config/syntax.md) | A configuration file does not parse | `operator` | `no` | `500` |
| [`pipelex.config.file_missing`](pipelex/config/file_missing.md) | A configuration file is missing | `operator` | `no` | `500` |
| [`pipelex.config.variable_missing`](pipelex/config/variable_missing.md) | A configuration variable is not set | `operator` | `no` | `500` |
| [`pipelex.config.credential_missing`](pipelex/config/credential_missing.md) | An inference backend has no credential | `operator` | `no` | `500` |
| [`pipelex.config.credential_refused`](pipelex/config/credential_refused.md) | A service refused the configured credential | `operator` | `no` | `500` |
| [`pipelex.config.dependency_missing`](pipelex/config/dependency_missing.md) | An optional dependency is not installed | `operator` | `no` | `500` |

## pipelex.plugin { #pipelex-plugin }

The plugins installed in the runtime.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.plugin.not_found`](pipelex/plugin/not_found.md) | No plugin provides the configured choice | `operator` | `no` | `500` |
| [`pipelex.plugin.broken`](pipelex/plugin/broken.md) | A plugin failed to load | `operator` | `no` | `500` |
| [`pipelex.plugin.conflict`](pipelex/plugin/conflict.md) | Two plugins claim the same slot | `operator` | `no` | `500` |
| [`pipelex.plugin.api_mismatch`](pipelex/plugin/api_mismatch.md) | A plugin targets another plugin API | `operator` | `no` | `500` |

## pipelex.deployment { #pipelex-deployment }

The policies of a runner deployment.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.deployment.orchestration_override_forbidden`](pipelex/deployment/orchestration_override_forbidden.md) | This deployment does not allow choosing the orchestration mode | `input` | `no` | `422` |
| [`pipelex.deployment.custom_code_requires_sandbox`](pipelex/deployment/custom_code_requires_sandbox.md) | Custom code needs a sandbox-hosted deployment | `operator` | `no` | `501` |
| [`pipelex.deployment.python_structures_refused`](pipelex/deployment/python_structures_refused.md) | Python structure classes are not allowed here | `method` | `no` | `422` |
| [`pipelex.deployment.token_claims_invalid`](pipelex/deployment/token_claims_invalid.md) | The token's claims cannot be used | `operator` | `no` | `500` |

## pipelex.docgen { #pipelex-docgen }

The document engines that print a PipeDocGen step's documents.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.docgen.engine_unavailable`](pipelex/docgen/engine_unavailable.md) | No document engine prints this here | `operator` | `no` | `501` |
| [`pipelex.docgen.template_invalid`](pipelex/docgen/template_invalid.md) | The document template cannot be used | `method` | `no` | `422` |
| [`pipelex.docgen.resource_refused`](pipelex/docgen/resource_refused.md) | The document names a file it may not read | `method` | `no` | `422` |
| [`pipelex.docgen.content_unprintable`](pipelex/docgen/content_unprintable.md) | The document's content cannot be printed | `input` | `no` | `422` |
| [`pipelex.docgen.print_timeout`](pipelex/docgen/print_timeout.md) | Printing the document took too long | `runtime` | `yes` | `504` |
| [`pipelex.docgen.template_warning`](pipelex/docgen/template_warning.md) | The document template may be faulty | `method` | `no` | none (warning) |

## pipelex.sandbox { #pipelex-sandbox }

The Daytona sandbox that runs a method's own code.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.sandbox.unavailable`](pipelex/sandbox/unavailable.md) | The Daytona sandbox could not be started | `runtime` | `yes` | `503` |

## pipelex.codegen { #pipelex-codegen }

Code generated from a method.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.codegen.output_conflict`](pipelex/codegen/output_conflict.md) | Codegen will not write there | `input` | `no` | `409` |
| [`pipelex.codegen.lock_invalid`](pipelex/codegen/lock_invalid.md) | The codegen lock is unreadable | `input` | `no` | `422` |
| [`pipelex.codegen.lock_unsupported`](pipelex/codegen/lock_unsupported.md) | The codegen lock needs a newer Pipelex | `operator` | `no` | `500` |
| [`pipelex.codegen.lock_not_found`](pipelex/codegen/lock_not_found.md) | No codegen lock in this directory | `input` | `no` | `404` |
| [`pipelex.codegen.drifted`](pipelex/codegen/drifted.md) | The generated code has drifted from its method | `input` | `no` | `409` |

## pipelex.connector { #pipelex-connector }

The toolsets a method's connectors offer a model.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.connector.tool_not_in_toolset`](pipelex/connector/tool_not_in_toolset.md) | The tool is not in the connector's toolset | `method` | `no` | `422` |

## pipelex.erasure { #pipelex-erasure }

The erasure of runs and methods.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.erasure.incomplete`](pipelex/erasure/incomplete.md) | The erasure left data behind | `runtime` | `yes` | `503` |

## pipelex.webhook { #pipelex-webhook }

The webhooks a caller registers to hear about its runs.

| Code | Title | Domain | Retry | Status |
|---|---|---|---|---|
| [`pipelex.webhook.delivery_failed`](pipelex/webhook/delivery_failed.md) | A webhook was not delivered | `input` | `yes` | `502` |
