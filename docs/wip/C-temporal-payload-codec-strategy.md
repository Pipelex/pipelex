# Temporal Payload Codec Strategy: Transparent Large Payload Offloading

> **Status**: Draft
> **Date**: 2026-03-23
> **Related**: [temporal-library-fix-proposals-v2.md](temporal-library-fix-proposals-v2.md), [library-as-execution-context.md](library-as-execution-context.md)

---

## 1. The Payload Size Problem

Temporal imposes a **2MB limit per individual payload** (each argument and return value) and a 4MB gRPC message limit. Two things in our architecture can exceed this:

- **Library context**: The collection of concepts and pipes needed for execution. Can be arbitrarily large depending on the library.
- **Working memory**: Runtime data being processed. Can include images, documents, and other large payloads.

This limit applies **equally to workflows and activities** — every individual input argument and output return value is capped. Moving data into activities does not escape the limit; it just relocates it.

---

## 2. Why Activities for Upload/Download Don't Work

The naive approach:

> "Put the large data in external storage. Use an activity to upload before dispatching, and another activity to download on the worker."

This fails for two reasons:

1. **Activities have the same 2MB per-payload limit.** An activity that returns the library context as its output hits the same cap. You've moved the problem back one step without solving it.

2. **Workflow code must be deterministic.** You can't do storage I/O directly in workflow `run()` methods. So you're forced into activities, which circles back to problem 1.

---

## 3. The Solution: PayloadCodec

Temporal's `PayloadCodec` operates at the **wire boundary** — outside the workflow sandbox, outside determinism rules, outside the payload size problem entirely.

### How it works

`PayloadCodec` intercepts every payload going to and from the Temporal server. It sits between your application code and the gRPC transport:

```
Application code                    PayloadCodec                  Temporal Server
───────────────                     ────────────                  ───────────────
pass WorkingMemory (50MB) ──► encode(): upload to S3,     ──► stores small S3 ref
                               replace with S3 key ref          in Event History

receive S3 ref             ◄── decode(): download from S3, ◄── reads S3 ref from
return WorkingMemory (50MB)     reconstruct original payload     Event History
```

The codec has two methods:

- **`encode(payloads)`**: Called on every outbound payload. If a payload exceeds a size threshold, upload it to external storage and replace it with a lightweight reference.
- **`decode(payloads)`**: Called on every inbound payload. If a payload is a storage reference, download the real data and reconstruct the original payload.

### Why it's transparent

Application code never changes. Workflows and activities pass `PipeJob`, `WorkingMemory`, `LibraryContext` — whatever size — as normal arguments. The codec handles offloading invisibly. No explicit upload/download logic anywhere in the business layer.

### Why it doesn't violate determinism

The codec runs **outside the workflow sandbox**. It is not subject to deterministic replay rules. Temporal's documentation and community discussions confirm:

- `PayloadCodec` does **not** need to be deterministic (unlike `PayloadConverter`, which runs inside the sandbox).
- The **encoded** form (the storage reference) is what gets stored in Event History.
- During **replay**, the worker receives encoded payloads from history and calls `decode()` again — so downloads happen during replay too.
- This is safe because the codec operates before/after the deterministic layer, and content-addressed storage (SHA256 key) guarantees the same key always returns the same data.

### Retention requirement

Since `decode()` is called during replay, the external storage must **retain offloaded payloads for the workflow's retention period**. If a workflow has a 30-day retention, the S3 objects must live at least 30 days.

---

## 4. Implementation Sketch (Python SDK)

```python
from typing import Sequence

from temporalio.api.common.v1 import Payload
from temporalio.converter import PayloadCodec

ENCODING_STORAGE_REF = b"binary/storage-ref"
SIZE_THRESHOLD = 1_000_000  # 1 MB — well under the 2 MB hard limit

class StoragePayloadCodec(PayloadCodec):
    """Offloads large payloads to external storage, replacing them with references."""

    def __init__(self, storage_provider: StorageProvider, prefix: str = "temporal-payloads/") -> None:
        self._storage = storage_provider
        self._prefix = prefix

    async def encode(self, payloads: Sequence[Payload]) -> list[Payload]:
        result: list[Payload] = []
        for payload in payloads:
            serialized = payload.SerializeToString()
            if len(serialized) < SIZE_THRESHOLD:
                result.append(payload)
                continue
            # Content-addressed: same data → same key → natural dedup
            key = self._prefix + sha256(serialized).hexdigest()
            await self._storage.upload(key, serialized)
            result.append(
                Payload(
                    metadata={"encoding": ENCODING_STORAGE_REF},
                    data=key.encode(),
                )
            )
        return result

    async def decode(self, payloads: Sequence[Payload]) -> list[Payload]:
        result: list[Payload] = []
        for payload in payloads:
            if payload.metadata.get("encoding") != ENCODING_STORAGE_REF:
                result.append(payload)
                continue
            key = payload.data.decode()
            original_bytes = await self._storage.download(key)
            original_payload = Payload()
            original_payload.ParseFromString(original_bytes)
            result.append(original_payload)
        return result
```

Registration on both client and worker:

```python
import dataclasses
import temporalio.converter

codec = StoragePayloadCodec(storage_provider=my_storage_provider)

data_converter = dataclasses.replace(
    temporalio.converter.default(),
    payload_codec=codec,
)

# Client side
client = await Client.connect("temporal-host:7233", data_converter=data_converter)

# Worker side — same data_converter
worker = Worker(client, task_queue="pipelex", data_converter=data_converter, ...)
```

The same `data_converter` (with the same codec) must be used on both the client and the worker. This is how `encode()` on the client side and `decode()` on the worker side stay in sync.

---

## 5. How This Simplifies the v2 Architecture

The v2 proposals ([temporal-library-fix-proposals-v2.md](temporal-library-fix-proposals-v2.md)) identified several concerns around payload size. Here's how the codec approach resolves them:

| v2 concern | Without codec | With codec |
|---|---|---|
| `LibraryContext` too large for workflow input | Must chunk, compress, or externalize manually | Transparent — pass it as a normal field |
| `WorkingMemory` with images exceeding 2MB | Explicit upload/download activities needed | Transparent — pass it as a normal argument |
| `raw_pipe_job_payload` size in `TemporalPipeJobEnvelope` | Must manage size carefully | Size is irrelevant — codec handles it |
| Need for explicit storage upload/download activities | Yes — adds complexity and latency | **No** — codec handles all byte-moving |
| Storage provider integration | Activity-level, per-workflow | Codec-level, once, for all workflows |

### What remains from v2

The codec solves the **payload size** problem. It does **not** solve the **library loading** problem. These are distinct:

- **Payload size**: "How do we get large data through Temporal's wire protocol?" → Codec.
- **Library loading**: "How do we get concepts and pipes registered in the worker's Python process before deserialization?" → Still needs the v2 approach (worker startup loading + deferred deserialization + `act_library_setup` activity).

The v2's `act_library_setup` activity is still required, but its job simplifies:

- **Before codec**: Responsible for both fetching library data AND loading it into the process.
- **After codec**: Only responsible for **loading the library into the process** (generating dynamic classes, populating the registry). The data arrives transparently through the codec.

The `TemporalPipeJobEnvelope` with deferred deserialization (v2 Option D) is still needed for the Layer 1 timing problem — dynamic classes must be registered before Kajson can deserialize the `PipeJob`. But the envelope's `library_context` field can now be arbitrarily large without concern.

---

## 6. Codec Server (for Observability)

Separately from the SDK-level `PayloadCodec`, Temporal supports a **Codec Server** — a standalone HTTP service that enables the Web UI and CLI to decode payloads for display.

| Aspect | SDK PayloadCodec | Codec Server |
|---|---|---|
| What it is | Class in your application code | Standalone HTTP service |
| Where it runs | Embedded in client and worker processes | Separate infrastructure |
| Purpose | Transparent encode/decode for all payloads | Enable Web UI and CLI to display decoded data |
| Endpoints | N/A (in-process) | `POST /encode` and `POST /decode` |
| Required? | Yes — for transparent offloading | Optional — for observability only |

The Codec Server typically runs the same codec logic. If we offload to S3, the Codec Server needs S3 access to decode payloads for display in the Temporal Web UI. This is a nice-to-have, not a blocker.

---

## 7. Future: Temporal's Native ExternalStorage

Temporal has an `ExternalStorage` / `StorageDriver` API in development that formalizes exactly this pattern:

```python
# NOT YET RELEASED — seen in API docs but not in temporalio 1.23.0
ExternalStorage(
    drivers=[my_s3_driver],
    payload_size_threshold=256 * 1024,  # default 256 KiB
    driver_selector=my_selector_fn,
)
```

The `StorageDriver` interface requires `store()` and `retrieve()` methods — essentially what our custom codec does. When this ships, we migrate from our custom `PayloadCodec` to the built-in `ExternalStorage` with minimal changes.

**Action**: Monitor `temporalio` releases for `ExternalStorage` availability. Until then, the custom `PayloadCodec` approach is the officially recommended pattern.

---

## 8. Integration with Pipelex Storage Providers

Our `StoragePayloadCodec` should use Pipelex's existing storage provider system rather than hardcoding S3. This means:

- The codec's storage backend is configured through Pipelex's standard configuration
- The same storage provider that handles other Pipelex storage needs handles temporal payload offloading
- Switching from S3 to GCS or another backend requires no codec changes

The codec is instantiated during Temporal client/worker setup, reading the storage provider configuration from Pipelex's config system.

---

## 9. Open Questions

- **Content-addressed dedup**: Using SHA256 of the payload as the storage key gives us natural deduplication — if the same library context is sent across multiple workflow runs, it's stored once. Is this sufficient, or do we need explicit cache management?
- **Cleanup policy**: S3 objects must outlive the workflow retention period. Should we use S3 lifecycle rules, or implement explicit garbage collection tied to workflow completion?
- **Threshold tuning**: 1MB is a safe default (well under the 2MB hard limit, leaving room for metadata). Should this be configurable per deployment?
- **Codec + Kajson interaction**: The codec operates on raw `Payload` protobuf objects, before Kajson deserialization. This means the Layer 1 timing problem (dynamic class registration) is unaffected by the codec — deferred deserialization is still needed. Confirm this doesn't introduce any ordering issues.
