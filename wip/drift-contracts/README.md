# Drift contracts — track folder

Working notes for the drift-contracts system (the shipped system itself is documented at `docs/contribute/drift-contracts.md`; the original design rationale at `../drift-contracts-design.md`).

- **`phase-3-verdict.md`** — the pilot verdict working doc: per-contract keep/narrow/mechanize/drop rulings, trigger repairs, new contracts, derived-check adoption. **The live document — awaiting Louis' rulings.**
- **`dogfood-log.md`** — one mandatory entry per `drift ack` (real-catch / clean-pass / friction). The pilot's primary evidence stream; stays mandatory per the verdict doc's E3.
- **`ack-record-gaps.md`** — two gaps in `.drift/acks/*.toml` as a data model, both found on a merge: the ack has no merge semantics (a merge invalidates both parents' acks by construction), and `--by`'s git-user default silently overwrote deliberate reviewer identities on every contract. Carries DECISION M1/M2 — **rule on these alongside the verdict doc**, since both get worse as the manifest grows.

Campaign-side evidence (the Drift Hunt) lives in `../drift-hunt/findings/SUMMARY.md` — its Handoff 1 is the drift-contract shortlist the verdict doc consumes.
