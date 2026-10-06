"""Applying ``FixOp`` patch operations to TOML documents, and committing the result to disk.

Two callers share this package: the ``.mthds`` fix loop (``pipelex.pipeline.fixes``) and the
configuration-migration engine (``pipelex.migration``). It is kernel-layer, and it sits here rather
than under either caller for that reason: the migration engine runs inside a kernel-layer boot that
meets a stale configuration file, so what it applies operations with must load no interpreter module
(``docs/contribute/hub-layering.md``).
"""
