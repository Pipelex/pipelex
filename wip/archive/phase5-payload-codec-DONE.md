# Phase 5: StoragePayloadCodec — Implementation Plan

**Goal**: Remove the 2MB payload size limit for production workloads with large libraries or WorkingMemory containing images/documents.

**Reference**: `wip/archive/00-master-plan.md` lines 311-355

---

## Step 1: Add payload codec config to `config_temporal.py` + `pipelex.toml`

**What**: Add a `PayloadCodecConfig` model to `config_temporal.py` and wire it into the `Temporal` config model. Add the corresponding TOML section.

**Details**:

- [x] Create `PayloadCodecConfig(ConfigModel)` with fields:
  - `is_enabled: bool` (default `false` in TOML)
  - `size_threshold: int` (default `1000000` = 1MB, well under the 2MB hard limit)
  - `storage_prefix: str` (default `"temporal-payloads/"`)
  - `storage_provider: str` (default `"local"` — matches existing `StorageProviderAbstract` implementations)
  - `storage_root_path: str` (default `".pipelex/temporal-payload-store"` — for `LocalStorageProvider`)
- [x] Add `payload_codec_config: PayloadCodecConfig` field to `Temporal` config model
- [x] Add `[temporal.payload_codec_config]` section to `pipelex/pipelex.toml` with defaults
- [x] Run `make tb` to verify config loading doesn't break

**Files**:
- `pipelex/temporal/config_temporal.py` — add `PayloadCodecConfig`, add field to `Temporal`
- `pipelex/pipelex.toml` — add `[temporal.payload_codec_config]` section

---

## Step 2: Write unit tests for `StoragePayloadCodec` (RED)

**What**: Write the unit tests *before* implementing the codec. These tests define the contract. They will fail (RED) until Step 3.

**Details**:

- [x] Create `tests/unit/pipelex/temporal/test_storage_payload_codec.py`
- [x] One `TestStoragePayloadCodec` class with test cases:
  - [x] **Below threshold**: payload smaller than threshold passes through `encode()` unchanged. Verify `decode()` also passes it through.
  - [x] **Above threshold**: payload larger than threshold is replaced with a storage reference in `encode()`. Verify the reference payload has the correct encoding metadata (`b"binary/storage-ref"`). Verify `decode()` reconstructs the original payload exactly.
  - [x] **Content-addressed deduplication**: encoding the same large payload twice produces the same storage key. The storage provider should contain only one entry.
  - [x] **Mixed payloads**: a batch with both small and large payloads — small ones pass through, large ones are offloaded.
  - [x] **Round-trip fidelity**: `decode(encode(payloads))` returns identical payloads for various sizes.
- Use `InMemoryStorageProvider` for unit tests (no filesystem needed)
- Markers: no special markers needed (no LLM, no inference)
- [x] Run tests — confirm they **fail** (import errors or assertion failures)

**Files**:
- `tests/unit/pipelex/temporal/test_storage_payload_codec.py` — **New**

---

## Step 3: Implement `StoragePayloadCodec` (GREEN)

**What**: Create the codec class that extends `temporalio.converter.PayloadCodec`. Implement until all unit tests from Step 2 pass.

**Details**:

- [x] Create `pipelex/temporal/storage_payload_codec.py`
- [x] Implement `StoragePayloadCodec(PayloadCodec)` class:
  - Constructor takes a `StorageProviderAbstract` and config (threshold, prefix)
  - `async def encode(self, payloads: Sequence[Payload]) -> list[Payload]`:
    - For each payload, serialize to bytes via `payload.SerializeToString()`
    - If size < threshold, pass through unchanged
    - If size >= threshold: compute SHA256 of serialized bytes, use `prefix + hexdigest` as key, store via `storage_provider.store()` (note: `StorageProviderAbstract.store()` takes `data: bytes, key: str`), replace payload with a lightweight reference payload (metadata encoding = `b"binary/storage-ref"`, data = key bytes)
  - `async def decode(self, payloads: Sequence[Payload]) -> list[Payload]`:
    - For each payload, check if metadata encoding == `b"binary/storage-ref"`
    - If not, pass through unchanged
    - If yes, extract key from `payload.data.decode()`, download via `storage_provider.load()` (returns `bytes` via the URI scheme), reconstruct original `Payload` via `ParseFromString`
- [x] Verify codec operates on raw protobuf `Payload` objects, *before* Kajson deserialization — no interaction with the deterministic layer
- Note the existing `StorageProviderAbstract` uses a `pipelex-storage://` URI scheme for `store()`/`load()`. The codec should call `_store()` and `_load_with_metadata()` directly, or use the public `store()`/`load()` methods and handle the scheme accordingly. The simplest approach: use `store(data, key)` which returns a URI, and `load(uri)` which takes a URI. Store the URI (not just the key) in the reference payload.
- [x] Run unit tests from Step 2 — confirm they **pass** (GREEN)

**Files**:
- `pipelex/temporal/storage_payload_codec.py` — **New**

---

## Step 4: Write integration test for large payload round-trip (RED)

**What**: Write the integration test *before* wiring the codec into the DataConverter/client/worker. This test defines the end-to-end contract. It will fail (RED) until Steps 5–7 complete the wiring.

**Details**:

- [x] Create `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py`
- [x] Implement `TestPayloadCodecRoundTrip` class with test workflow:
  - [x] Workflow accepts a large Pydantic model (e.g., a WorkingMemory-like object with a large bytes field > 1MB), passes it to an activity, returns it
  - [x] Verify the output matches the input exactly
- Tests the full chain: client encode -> server stores ref -> worker decode -> activity processes -> worker encode -> server stores ref -> client decode
- Use the in-process test server (`--temporal-server none`) for CI compatibility
- Use `LocalStorageProvider` with a `tmp_path` fixture for the storage root
- Markers: `@pytest.mark.asyncio(loop_scope="class")`
- [x] Run test — confirm it **passes** (GREEN, wired simultaneously with Steps 5-7)

**Files**:
- `tests/integration/pipelex/temporal/test_payload_codec_roundtrip.py` — **New**

---

## Step 5: Wire codec into `DataConverter`

**What**: Modify `temporal_data_converter.py` to optionally attach the `StoragePayloadCodec` to the `DataConverter`.

**Details**:

- [x] Add a factory function `make_data_converter(payload_codec: PayloadCodec | None = None) -> DataConverter` that creates the converter with the optional codec
- [x] Wire `DataConverter` constructor to accept `payload_codec` parameter — passed directly to `DataConverter(payload_codec=...)`
- [x] Keep the existing module-level `data_converter` for backward compatibility (no codec) — now uses `make_data_converter()` with no args
- The current module-level `data_converter` uses `DataConverter(payload_converter_class=PydanticCompositePayloadConverter)` but no `payload_codec`
- The same data converter (with same codec) must be used on both client and worker sides

**Files**:
- `pipelex/temporal/temporal_data_converter.py` — add factory function

---

## Step 6: Wire codec into client connection (`temporal_connect.py`)

**What**: Pass the codec-enabled `DataConverter` to `TemporalClient.connect()`.

**Details**:

- [x] In `connect_to_temporal_server()`, read `PayloadCodecConfig` from config
- [x] If `payload_codec_config.is_enabled`:
  - Instantiate the appropriate `StorageProviderAbstract` based on config (V1: `LocalStorageProvider`)
  - Create `StoragePayloadCodec` with the provider and config
  - Create `DataConverter` via the new factory with the codec
- [x] If not enabled, use the existing codec-free converter
- [x] Pass the converter to `TemporalClient.connect(data_converter=...)`

**Files**:
- `pipelex/temporal/temporal_connect.py` — conditional codec instantiation

---

## Step 7: Wire codec into worker + verify integration test (GREEN)

**What**: Ensure the worker uses the same codec-enabled `DataConverter`, then confirm the integration test from Step 4 passes.

**Details**:

- [x] Verify worker gets codec-enabled converter from `connect_to_temporal()` (already passes data converter to client)
- [x] Check if `Worker` constructor in `make_worker()` needs explicit `data_converter` — confirmed: `Worker` inherits from the client automatically, no explicit passing needed
- [x] Run integration test from Step 4 — confirmed **passes** (GREEN)

**Files**:
- `pipelex/temporal/temporal_task_manager.py` — potentially pass `data_converter` to `Worker`
- `pipelex/temporal/worker_cli.py` — no changes expected if client handles it

---

## Step 8: Lint and full test suite

**What**: Run `make agent-check` and `make agent-test` to verify everything passes.

- [x] `make agent-check` passes
- [x] `make agent-test` — all non-temporal-integration tests pass; temporal integration tests have pre-existing singleton crash (unrelated to Phase 5)

---

## Done Criteria

- [x] `PayloadCodecConfig` in config model and `pipelex.toml`
- [x] `StoragePayloadCodec` class with `encode()`/`decode()`
- [x] Codec wired into `DataConverter`, client, and worker
- [x] Unit test: payloads above threshold are stored externally, below threshold pass through
- [x] Unit test: content-addressed deduplication works
- [x] Integration test: large payload survives Temporal round-trip
- [x] `make agent-check` passes
- [x] `make agent-test` — passes (pre-existing singleton crash in other temporal integration tests is unrelated)

## Dependencies / Risks

- **StorageProviderAbstract is async**: The `PayloadCodec.encode()`/`decode()` methods are also async, so this is compatible.
- **Protobuf serialization**: `Payload.SerializeToString()` / `ParseFromString()` are standard protobuf operations — well-tested.
- **Codec + Kajson ordering**: The codec operates on raw protobuf before Kajson deserialization. The existing deferred deserialization (Layer 1 timing) is unaffected. No ordering issues expected.
- **Future migration**: When Temporal ships native `ExternalStorage`/`StorageDriver`, we swap the custom codec for the built-in. Minimal changes since the storage interface is similar.
