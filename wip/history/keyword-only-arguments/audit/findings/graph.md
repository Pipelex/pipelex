# Suspects — package `graph`

Reviewed: 40 Section A + 12 primitive lone-subjects. Suspects: 1.

## High confidence

_(none)_

## Medium / low confidence

- `pipelex/graph/graph_tracer_manager.py:266` — `GraphTracerManager.on_pipe_end_success` — `def on_pipe_end_success(self, lookup_key: str, *, node_id: str | None, ...)` — `lookup_key` is a registry dispatch key used to route to the correct `GraphTracer` instance via `self._get_tracer(lookup_key)`; the semantic subject is `node_id` (the node whose execution ended), which sits in the keyword args. Same pattern applies to `on_pipe_end_error` (line 325), `register_execution_data` (line 304), `add_edge` (line 360), `register_controller_output` (line 389), `register_batch_item_extraction` (line 411), `register_batch_aggregation` (line 440), and `register_parallel_combine` (line 469). All call sites already pass `lookup_key=` as a keyword argument (e.g. `pipe_abstract.py:116`), so no opacity exists today. The case for making `lookup_key` keyword-only too is that it is a dispatch/lookup concern rather than the semantic object of the operation, and the naming asymmetry between these manager methods and the underlying `GraphTracerProtocol` methods (which take `node_id` positionally) is a mild source of confusion. Low confidence overall — the call-site pattern is already keyword-explicit, and `lookup_key` as first-positional is a coherent "which tracer" discriminant. Suggested fix if desired: make `lookup_key` keyword-only across all eight manager dispatch methods (fully keyword-only signatures), mirroring the symmetry with the protocol layer.
