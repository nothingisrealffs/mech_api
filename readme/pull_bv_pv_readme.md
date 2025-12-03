# BV/PV Lookup & pull.py Guide

This guide explains how BV/PV values are fetched via `pull.py`, how jobs are queued, and how to run the worker to populate values.

## Components
- `pull.py`: CLI helper that fetches BV/PV for a unit (mech/vehicle/aero/etc.) and prints JSON.
- `bv_pv_worker.py`: consumes `bv_pv_job` rows and calls `pull.py` to fill `bv`/`pv` in the database.
- Ingest (MTF/BLK): can request BV/PV in two modes:
  - `enqueue` (default): create a job row; worker must process it.
  - `sync`: call `pull.py` inline during ingest/test.

## Using pull.py Directly
```bash
python pull.py --mech "Enforcer" --variant "ENF-4R"
# or, for vehicles (MUL type 19):
python pull.py --mech "APC (Hover)" --variant "LRM" --types 19
```
The script returns JSON with `bv` and `pv` fields when found.

## BV/PV Modes in the App
- `enqueue`: default for ingest/test. Adds a `bv_pv_job` row; nothing happens until the worker runs.
- `sync`: call `pull.py` immediately. Available in the TUI test pipeline prompt; can also be passed to ingestion functions directly.

## Running the Worker
From the TUI:
- Utilities → Run BV/PV Worker (choose looping or one-shot; honors current DB backend).

From the CLI:
```bash
# SQLite (default)
python bv_pv_worker.py --loop

# Postgres (requires POSTGRES_DSN set in mtf_ingest.py)
python bv_pv_worker.py --loop --use-postgres
```
- Omit `--loop` to process current pending jobs and exit.
- `--limit` controls batch size; `--sleep` controls delay between polling when looping.

## When to Use Each Mode
- Quick, single-file checks: use `sync` (e.g., Test Random File Pipeline → choose `sync`).
- Bulk ingest: keep `enqueue` and run the worker in the background.

## Troubleshooting
- BV/PV stays null: make sure the worker ran (enqueue) or rerun with `sync`.
- No jobs processed: confirm `bv_pv_job` table has rows and that the worker is pointing to the same DB (SQLite vs Postgres).
- pull.py errors: run `pull.py` directly to confirm the unit/variant you’re requesting.
