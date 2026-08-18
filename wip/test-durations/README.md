# Test durations — track folder

Working notes for the `.test_durations` refresh work (the shipped system is documented at `docs/contribute/test-duration-map.md`).

- **`what-we-built.html`** — the explainer for co-developers: why the refresh went incremental, the measurements that drove it, what to run, and how it was verified. **Start here.**

Context in one line: `make store-test-durations` used to run the whole suite at every release and rewrite ~21,000 lines; it now measures only the tests missing from the map, because missing coverage is what unbalances the CI shards while stale values are nearly free.
