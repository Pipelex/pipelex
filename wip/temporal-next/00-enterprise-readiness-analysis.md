# Pipelex × Temporal: Enterprise Readiness Analysis

Strategic assessment of the current Temporal integration and a proposed phasing plan to bring it to a level of technological readiness that would clear an enterprise CIO review.

Scope of audit: `pipelex/temporal/` (30 core files), `docs/distributed-execution/` (5 docs), `pipelex/pipelex.toml` config surface, `tests/` coverage, `.github/workflows/` CI gating, and `wip/temporal-primitives/` planning state.

---

## 1. Where we stand today

**Strong fundamentals (TRL ~6–7):**

- Clean separation of concerns across the module: management (`temporal_manager`, `temporal_hub`), execution (`temporal_task_manager`, `worker_cli`), routing (`config_temporal.py` — three-layer baseline → queue → handle overlays), serialization (`temporal_data_converter`, `codec/`), and observability (`tprl/observability.py`, `tprl/namespace_check.py`).
- Policy-rich configuration: server profiles, worker scopes, named runtime profiles, per-activity / per-handle routing, search-attribute pre-flight validation at worker boot with "did you mean?" UX.
- Replay safety taken seriously: deterministic IDs, sandbox-aware logging (`sandbox_manager.py`), UTF-8-safe summary/details truncation.
- The five docs under `docs/distributed-execution/` cover the operational story for single-tenant deployments end-to-end.

Phases 1–6 of `wip/temporal-primitives/` are shipped; the only deferred item is the `WorkflowExecutionError → ApplicationError` cleanup.

---

## 2. Critical gaps a CIO will flag

Ordered by how loudly they'll come up in an enterprise security / procurement review:

1. **Authentication is too narrow.** `temporal_connect.py` supports only static API keys (env var or secret provider). No mTLS, no OAuth/OIDC, no custom CA bundle. Hard blocker for regulated industries and most large enterprises with PKI/SSO requirements.

2. **Payload codec has no client-side encryption.** `codec/storage_payload_codec.py` offloads payloads to GCS/S3/local but relies entirely on the backend's at-rest encryption. A stolen storage backup is plaintext customer data. No envelope encryption, no KMS hook, no field-level PII masking. Static summary/details builders dump pipe inputs into the Temporal UI with no redaction allowlist.

3. **The project's own error-handling rule is violated in workflow-critical paths.** `tprl_pipe/wf_pipe_router.py` has multiple `except Exception` blocks; `tprl_pipe/act_assemble_graph.py` has one labeled "TODO: wip — do not catch all exceptions". CLAUDE.md explicitly forbids this. Adversarial reviewers and auditors anchor on exactly these.

4. **No OpenTelemetry / no metrics exporter.** Observability is Temporal-UI-centric. Enterprises require traces into their own APM (Datadog, New Relic, Dynatrace, Honeycomb) and metrics into Prometheus/StatsD: queue depth, retry rate, activity duration histograms, codec offload latency, slot saturation. None of that is wired today.

5. **CI only runs the in-process test server.** The default `--temporal-server none` means no regression coverage against a real Temporal server — version-drift, cluster-failover, and real-RPC semantics aren't validated in CI.

6. **Test coverage is thin in core modules.** Codec encode/decode, dispatch resolution, observability builder, error classification, config composition, and the search-attribute pre-flight have no unit tests. Integration tests cover happy paths well; no chaos tests (worker crash mid-activity, server unreachable, retry exhaustion, replay non-determinism, cancellation propagation).

7. **No multi-tenant admission control.** `UserId` / `DomainCode` search attributes are informational. There's no gate that says "tenant X may only invoke this pipe list", no per-tenant quotas, no per-tenant rate limit, and the codec doesn't verify `user_id` matches the authenticated submitter before writing storage keys.

8. **No DR / BCP story.** Docs are silent on namespace replication, RTO/RPO, codec-storage cross-region replication, backup/restore. "What happens if our primary region goes down?" has no published answer.

9. **No upgrade / rolling-deployment guidance.** Worker versioning, sticky-queue drain, blue/green via task queues — none documented. This is the #1 ops question for production rollouts.

10. **Smaller but real:** hardcoded sandbox `passthrough_modules` list; `WorkerRuntimeProfile.tuning_mode = RESOURCE_BASED` is reserved but raises at config validation (creates confusion); per-queue `rate_limit` is cluster-wide and racy when multiple workers publish different values.

---

## 3. Proposed phasing to TRL 9

A 6-phase ladder, each phase with a coherent CIO-facing message and a hard exit gate. Phases 0–2 are the bulk of the lift; 3–5 are productization.

### Phase 0 — Hygiene & test hardening *(foundation; no new features)*

**Why:** before shipping enterprise primitives, the existing surface must pass its own rules and have a regression net.

- Replace every `except Exception` in `pipelex/temporal/` with typed catches (priority: `tprl_pipe/wf_pipe_router.py`, `tprl_pipe/act_assemble_graph.py`).
- Resolve open TODOs (`temporal_task_manager.py` sandbox-logger note; conftest `Pipelex.make()` heavy-boot note).
- Add unit tests for: codec encode/decode + path-traversal sanitization, dispatch resolution (baseline → queue → handle merge), observability builders (UTF-8 truncation), error classification, search-attribute validator.
- Add chaos-style integration tests: worker crash mid-activity, server disconnect & reconnect, retry-policy exhaustion, replay non-determinism, child-workflow cancellation propagation, signal/query round-trip.
- Add a CI matrix entry that runs the integration suite against a real Temporal server (containerized) alongside the in-process one.
- **Eliminate remaining config reads inside workflow code** (flagged by PR #891 review — chatgpt-codex-connector). The submitter-side pattern is already in place for `WorkflowExecutorFactory` (bypassed inside workflows) and for `TemporalManager.session_id` (`stamp_submitter_session_id`), but two call paths still re-derive options from `get_config()` at workflow runtime, which would diverge on replay after any config edit:
    - `pipelex/temporal/tprl/observability.py:104-107` — `build_search_attributes` reads `get_config().temporal.search_attributes` (`enabled` flag + `attributes` list). Toggling either between deploys changes the recorded `StartChildWorkflowExecution` command on replay. The docstring already claims the helper is "a pure function" — making it actually pure requires snapshotting the enabled attribute names at the submitter boundary (analogous to `stamp_submitter_session_id`) and carrying them on `PipeJob` / `JobMetadata`. Affects every in-workflow caller: `wf_pipe_run.py:57`, `temporal_pipe_router.py:85`.
    - `pipelex/temporal/tprl_content_generation/content_generator_in_workflow.py` — every `make_*` method calls `worker_config.resolve_dispatch(..., queue_options_by_queue=get_config().temporal.queue_options, is_traced=get_config()...)` inside workflow code, so changing routing, queue options, or `is_dispatch_resolution_traced` re-derives a different `task_queue` / timeout / retry policy on replay and fails the workflow task. The same class of issue is acknowledged at `workflow_caller.py:179+` for child-workflow options; activity dispatch needs the equivalent treatment. Either snapshot the resolved dispatch options per activity at the submitter boundary, or freeze the relevant config blocks into the workflow input.

**Exit:** zero `except Exception` in `temporal/`; zero `get_config()` reads in workflow code paths (enforced by an AST scanner extension); CI green on real server; coverage report published per PR.

### Phase 1 — Security baseline *(unblocks CISO)*

**Why:** today the deal-breakers for any enterprise procurement are authentication and payload encryption.

- mTLS support in `TemporalServerConfig`: client cert/key paths, custom CA bundle, configurable cipher suites.
- OAuth/OIDC token auth as an alternative to static API keys; hot-reload on rotation without worker restart.
- Envelope encryption in `StoragePayloadCodec`: KMS-managed DEKs, pluggable provider (AWS KMS, GCP KMS, Azure Key Vault, HashiCorp Vault); key-ID stored in payload metadata for rotation.
- PII handling: declarative redaction allowlist for `build_static_details` / `build_static_summary`; documented "what goes into search attributes" policy.
- Codec admission check: verify `user_id` matches authenticated submitter before storage write.
- SBOM generation + CVE scan in CI (`pip-audit` or Grype + Syft); dependency pinning policy.
- Published threat model document; external pen-test against a reference deployment.

**Exit:** mTLS + at-rest envelope encryption working in a reference deployment; pen-test report with no high/critical findings; SBOM in releases.

### Phase 2 — Observability & SRE-grade telemetry

**Why:** enterprise ops teams refuse to operate what they can't see in their existing tools.

- OpenTelemetry instrumentation: spans from submitter → parent workflow → child workflow → activity, with `pipeline_run_id` as trace correlation key.
- OTLP exporter wired through `temporal_hub`; documented Datadog / New Relic / Honeycomb config.
- Prometheus metrics: queue depth, codec offload/restore latency p50/p95/p99, retry rate per activity, slot saturation, payload-size histogram, graph-assembly failures.
- Structured JSON logging mode in `log_formatter.py` (extending existing prefix injection); correlation IDs everywhere.
- Shipped artifacts: Grafana dashboard JSON, PromQL alert recipes (orphaned workflows, queue lag, codec storage outage), runbooks for the top failure modes.

**Exit:** demoable end-to-end trace from API request to LLM call; Grafana board + alert recipes shipped; runbook set published.

### Phase 3 — Operational excellence

**Why:** CIOs ask "can I deploy this on Tuesday afternoon without paging anyone?"

- Rolling-upgrade strategy doc + reference: Temporal Worker Versioning, sticky-queue drain, parallel task queues for blue/green.
- Capacity planning guide derived from a published load-test harness (req/s → worker count → runtime profile sizes per activity class).
- Implement `WorkerRuntimeProfile.tuning_mode = RESOURCE_BASED` (or remove the enum value if not committed).
- Auto-scaling reference: KEDA + Temporal queue-lag metric, sample helm chart.
- Config drift CLI: `pipelex worker diff` to compare running config vs canonical.
- Per-worker rate-limit reconciliation (eliminate the "latest writer wins" race in per-queue rate limit).
- Document an SLO/SLI catalog: latency SLOs per activity class, queue saturation SLOs, error-budget framing.

**Exit:** load-test report; SLO catalog published; reference helm chart; rolling-upgrade tested end-to-end.

### Phase 4 — Multi-tenancy & governance

**Why:** enterprises onboard once and run many tenants; the platform must enforce isolation, not document it.

- Per-tenant RBAC at submission: tenant → allowed pipe list; codec validates scope.
- Quota enforcement: per-tenant concurrent-workflow cap, per-tenant queue rate-limit overlay.
- Cost attribution: per-tenant counters for activity-seconds, payload bytes, LLM tokens (extends telemetry already partially present).
- Data residency: per-tenant codec storage region + KMS key.
- Retention policies: configurable per `pipeline_run_id` age; automatic codec garbage-collection job.
- Audit log sink: Kafka/SIEM-bound stream covering workflow lifecycle + admin actions (worker config reload, codec key rotation).
- Reference deployment patterns: namespace-per-tenant, shared-namespace-with-isolation; admission control on both.

**Exit:** reference multi-tenant deployment with chargeback report; auditor-friendly event stream demonstrably feeding a SIEM.

### Phase 5 — Disaster recovery & business continuity

**Why:** any CIO sign-off requires a documented RTO/RPO and a tested DR drill.

- Multi-region active/passive pattern with Temporal namespace replication; documented submitter behavior during failover.
- Codec storage cross-region replication recipes (S3 CRR, GCS dual-region, Azure GRS).
- Backup/restore runbook for codec storage + a sample restore validator.
- DR drill harness: scripted chaos test forcing namespace failover, asserting in-flight workflows resume.
- Documented retention policies aligned to common compliance regimes (GDPR, HIPAA, PCI tier).

**Exit:** DR drill log demonstrating an explicit RTO and RPO target on the reference deployment.

### Phase 6 — Certification & productization *(TRL 9 marker)*

- SOC 2 Type II readiness; ISO 27001 control mapping doc.
- HIPAA / PCI tier guidance with concrete configurations.
- Customer-facing security whitepaper.
- Versioned compatibility matrix: Pipelex × Temporal Python SDK × Temporal Server; LTS branch policy.
- At least one reference customer running this at production scale and willing to be quoted.

**Exit:** external attestation; published compatibility matrix; reference customer in production for an extended period.

---

## 4. Recommendation

If we sequence this, **Phase 0** is a non-negotiable prerequisite — it's mostly cleanup of stated rules and missing tests, and it makes everything after it cheaper. Then **Phase 1 and Phase 2 in parallel** unblock the two distinct stakeholders (CISO and SRE) who together account for the bulk of enterprise procurement friction. Phases 3–6 are best paced against actual customer demand.

The single highest-leverage item across all phases is probably **envelope-encrypted payload codec with KMS pluggability** (Phase 1) — it converts the integration from "trust the backend" to "we own the data plane", which is the framing CIOs reward.
