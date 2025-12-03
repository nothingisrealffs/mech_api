# BattleTech Data Toolkit

This repo ingests BattleTech unit data (MTF for mechs, BLK for everything else) into a database and gives you a terminal UI to run the pipeline, resolve equipment, and populate BV/PV values. SQLite is the default; Postgres is optional.

## What’s Here
- `main_tui.py`: interactive console to ingest, resolve, finalize, run BV/PV lookups, and manage the database.
- `mtf_ingest.py`: mech parser/ingester.
- `blk_ingest.py`: BLK ingester for vehicles, aerospace, battle armor, and infantry.
- `load_equipment_csv.py`: loads canonical weapons/equipment and common aliases.
- `bv_pv_worker.py`: processes queued BV/PV lookup jobs (uses `pull.py`).
- `data/`: drop source files into subfolders (`mechs`, `vehicles`, `aerospace`, `battlearmor`, `infantry`, `weapons` for CSVs).

## Database Options
- SQLite (default): `mech_data_test.db` in the repo root.
- Postgres: set `POSTGRES_DSN` in `mtf_ingest.py` and enable it from the TUI “Data / Database” menu (Switch to Postgres).

## Quickstart
1) Install dependencies: `pip install -r requirements.txt`
2) Place files under `data/`:
   - Mechs: `data/mechs/*.mtf`
   - BLK units: `data/{vehicles|aerospace|battlearmor|infantry}/*.blk`
   - Equipment CSVs: `data/weapons/battletech_equipment.txt`, `battletech_clan_equipment.txt`, `battletech_is_ammo.txt`, `battletech_engine_tonnage.txt`
3) Run the TUI: `python main_tui.py`
4) In the TUI:
   - Data/DB → Load weapons/equipment (once per database)
   - Ingestion & Processing → Ingest Data (MTF/BLK)
   - Ingestion & Processing → Resolve Staging (match weapons/components)
   - Ingestion & Processing → Finalize Pending Transactions
   - Ingestion & Processing → Test Random File Pipeline (choose BV/PV mode: `enqueue` to queue jobs, `sync` to call `pull.py` inline)
   - Utilities → Run BV/PV Worker (to process queued jobs)
   - Data/DB → Rebuild SQLite or Switch to Postgres as needed

## BV/PV Lookups
- Modes during ingest: `enqueue` (default; creates `bv_pv_job` rows) or `sync` (calls `pull.py` immediately).
- To process queued jobs, run `python bv_pv_worker.py --loop` (or trigger from the TUI Utilities menu). Use `--use-postgres` when pointing at Postgres.

## Workflow Tips
- Load equipment CSVs before resolving/finalizing to minimize unresolved tokens.
- Use the test pipeline to sanity-check ingestion, resolution, and BV/PV behavior without guessing which file to try.
- The status panel shows unresolved tokens, pending slots, and totals for quick health checks.

## Troubleshooting
- “No files found”: confirm `data/` subfolders exist beside `main_tui.py`.
- Unresolved weapons: load equipment CSVs; add aliases if needed.
- BV/PV stay null: run the worker (enqueue mode) or rerun test/ingest with `sync` mode to call `pull.py`.
