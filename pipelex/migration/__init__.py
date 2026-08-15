"""The configuration-migration engine and the data it reads.

A **surface** is one family of user-owned TOML files with one schema version and one ledger.
This package holds the surface registry, the fingerprint that projects a surface's model tree
into a comparable shape, the ledger data models, and the coverage check that forces a schema
change to record what it did.

The contract this package implements is `docs/migration-ledger.md`, and it is normative — read
it before changing anything here.
"""
