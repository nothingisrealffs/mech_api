# Setup Guide

Follow these steps to get the BattleTech data toolkit running with the TUI.

## Prerequisites
- Python 3.10+ (with pip)
- Git, sqlite3 (built-in on macOS/Linux), and optional Postgres
- Local files placed under the repo’s `data/` folder

## Install
1) Clone or unpack the repo.
2) Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Prepare Data
- Mechs (MTF): `data/mechs/*.mtf`
- BLK units (vehicles/aero/battle armor/infantry): `data/{vehicles|aerospace|battlearmor|infantry}/*.blk`
- Equipment CSVs (recommended before resolving/finalizing):
  - `data/weapons/battletech_equipment.txt`
  - `data/weapons/battletech_clan_equipment.txt`
  - `data/weapons/battletech_is_ammo.txt`
  - `data/weapons/battletech_engine_tonnage.txt`

## Database Choice
- Default: SQLite at `mech_data_test.db` in the repo root.
- Postgres: set `POSTGRES_DSN` in `mtf_ingest.py`, then switch inside the TUI via Data / Database → Switch to Postgres.

## Run the TUI
```bash
python main_tui.py
```

### TUI Menus (grouped)
- **Ingestion & Processing**
  - Ingest Data (MTF/BLK)
  - Resolve Staging (match weapons/components)
  - Finalize Pending Transactions
  - Test Random File Pipeline (choose BV/PV mode: `enqueue` to queue jobs, `sync` to call `pull.py` inline)
- **Data / Database**
  - Load Weapons/Equipment (CSVs)
  - View Unresolved Weapons
  - Database Status
  - Rebuild SQLite (delete & recreate)
  - Switch to Postgres for this session
- **Utilities**
  - Run BV/PV Worker (process queued jobs)
  - Start API Server

## BV/PV Lookups
- Ingest/test BV/PV mode:
  - `enqueue` (default): creates `bv_pv_job` rows; requires the worker to populate BV/PV.
  - `sync`: calls `pull.py` immediately for BV/PV.
- Run the worker manually or via TUI:
  ```bash
  python bv_pv_worker.py --loop            # SQLite
  python bv_pv_worker.py --loop --use-postgres  # Postgres
  ```

## Recommended Flow
1) Load equipment CSVs.
2) Ingest MTF/BLK files.
3) Resolve staging, then finalize.
4) Run BV/PV worker (if using enqueue mode) or use sync mode for one-off checks.
5) Use the test pipeline to sanity-check a random file end-to-end.

## Troubleshooting
- **No files found**: confirm `data/` subfolders exist and contain files.
- **Unresolved weapons**: load equipment CSVs; add aliases as needed.
- **BV/PV still null**: run the worker (enqueue) or rerun with sync mode.
