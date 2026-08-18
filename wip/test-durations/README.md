# Test durations — track folder

Working notes for the `.test_durations` refresh work (the shipped system is documented at `docs/contribute/test-duration-map.md`).

- **`what-we-built.html`** — the explainer for co-developers: why the refresh went incremental, the measurements that drove it, what to run, and how it was verified. **Start here.**
- **`pr-1120-review-notes.md`** — the one review-agent finding from PR #1120 that was deferred rather than fixed: how much argv headroom the `FULL_RUN_RATIO` threshold actually leaves, and what would trigger revisiting it.

Context in one line: `make store-test-durations` used to run the whole suite at every release and rewrite ~21,000 lines; it now measures only the tests missing from the map, because missing coverage is what unbalances the CI shards while stale values are nearly free.
