# MTF Ingestion Guide

This guide covers ingesting mech MTF files, resolving equipment, and handling BV/PV for mechs.

## Folder Layout
- Place mech files in `data/mechs/*.mtf` (case-insensitive extension).

## Ingest via TUI
1) Run `python main_tui.py`.
2) Ingestion & Processing → Ingest Data → Mechs (MTF).
3) After ingest, run Resolve Staging, then Finalize Pending Transactions to create finalized slots and weapon instances.

## BV/PV Handling for Mechs
- Modes (shared with BLK ingest):
  - `enqueue` (default): add a `bv_pv_job` row; requires the worker to populate BV/PV.
  - `sync`: call `pull.py` immediately during ingest/test.
- TUI: Ingestion & Processing → Test Random File Pipeline lets you choose `enqueue` or `sync` for a one-off mech test.
- Worker: Utilities → Run BV/PV Worker (or run `python bv_pv_worker.py --loop`).

## Equipment Resolution
- Load equipment CSVs first (Data / Database → Load Weapons/Equipment) to maximize weapon resolution.
- Resolve Staging matches weapons/aliases and marks component slots; Finalize creates slots and weapon instances.

## CLI Ingest (optional)
You can call `mtf_ingest.py` directly if needed:
```bash
python mtf_ingest.py --folder data/mechs --bv-pv-mode enqueue   # or sync
# Add --use-postgres to point at Postgres DSN configured in mtf_ingest.py
```

## Tips
- Use Test Random File Pipeline (`sync` mode) to verify BV/PV and resolution for a single mech quickly.
- Keep the BV/PV worker running during bulk ingest if you stay in `enqueue` mode.
- Add weapon aliases if you see unresolved tokens after resolution.

## Troubleshooting
- “No files found”: ensure `data/mechs` exists and contains `.mtf` files.
- Many unresolved weapons: load equipment CSVs; add aliases as needed.
- BV/PV null: run with `sync` or process the queue with the worker.
