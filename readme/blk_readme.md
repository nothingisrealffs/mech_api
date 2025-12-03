# BLK Ingestion Guide

BLK files cover every non-mech unit: vehicles, aerospace, battle armor, and infantry. This guide explains how to place files, ingest them, and resolve equipment within the TUI.

## Folder Layout
- `data/vehicles/*.blk`
- `data/aerospace/*.blk`
- `data/battlearmor/*.blk`
- `data/infantry/*.blk`

The TUI treats all BLK types as a single group for stats, but you can ingest each folder individually or all at once.

## Ingestion via TUI
1) Run `python main_tui.py`.
2) Ingestion & Processing → Ingest Data.
3) Choose a specific BLK folder or “All BLK files” to process vehicles, aerospace, battle armor, and infantry in one pass.

## BV/PV Handling
- BLK ingest accepts a BV/PV mode, inherited from the same defaults as mechs:
  - `enqueue` (default): creates `bv_pv_job` rows for the BV/PV worker. BLK units use MUL type 19.
  - `sync`: calls `pull.py` immediately for BV/PV lookup.
- To process queued jobs, run the worker:
  ```bash
  python bv_pv_worker.py --loop            # SQLite
  python bv_pv_worker.py --loop --use-postgres  # Postgres
  ```
  or use Utilities → Run BV/PV Worker in the TUI.

## Equipment Resolution
- Load equipment CSVs first (Data / Database → Load Weapons/Equipment) to maximize resolution.
- After ingest, run Resolve Staging, then Finalize Pending Transactions to create finalized slots and weapon instances.

## Test Pipeline
- Use Ingestion & Processing → Test Random File Pipeline to pick a random BLK or MTF file and run ingest → resolve → finalize.
- Choose `sync` to test BV/PV lookups inline, or `enqueue` to verify the queue/worker flow.

## Troubleshooting
- Unresolved equipment: ensure equipment CSVs are loaded; add aliases if necessary.
- BV/PV still null: run the worker (enqueue mode) or rerun with sync mode to call `pull.py` directly.
