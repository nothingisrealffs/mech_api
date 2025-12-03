#!/usr/bin/env python3
"""
Simple worker to process queued BV/PV lookup jobs asynchronously.
Jobs are enqueued by mtf_ingest.py / blk_ingest.py when bv-pv-mode=enqueue.
This worker reuses pull.py via the existing fetch_bv_pv_from_pull helper.
"""

import argparse
import time
from datetime import datetime

from mtf_ingest import (
    Base,
    BvPvJob,
    fetch_bv_pv_from_pull,
    get_engine_and_session,
    USE_POSTGRES,
)


def fetch_next_jobs(session, limit: int):
    return session.query(BvPvJob).filter(BvPvJob.status == "pending").order_by(BvPvJob.created_at.asc()).limit(limit).all()


def process_job(session, job: BvPvJob):
    job.status = "processing"
    job.attempts = (job.attempts or 0) + 1
    job.updated_at = datetime.utcnow()
    session.commit()

    try:
        bv_val, pv_val = fetch_bv_pv_from_pull(job.name, job.variant, mul_type=job.mul_type)
        if bv_val is None and pv_val is None:
            job.status = "failed"
            job.last_error = "no data returned"
        else:
            job.bv = bv_val
            job.pv = pv_val
            job.status = "done"
            job.last_error = None
    except Exception as e:
        job.status = "failed"
        job.last_error = f"{type(e).__name__}: {e}"
    finally:
        job.updated_at = datetime.utcnow()
        session.commit()


def main():
    parser = argparse.ArgumentParser(description="Process BV/PV lookup jobs enqueued during ingest.")
    parser.add_argument("--limit", type=int, default=10, help="Number of jobs to process per batch")
    parser.add_argument("--loop", action="store_true", help="Keep polling for new jobs")
    parser.add_argument("--sleep", type=int, default=5, help="Seconds to sleep between polls when looping")
    parser.add_argument("--use-postgres", action="store_true", help="Use PostgreSQL (overrides USE_POSTGRES)")
    args = parser.parse_args()

    use_postgres = USE_POSTGRES or args.use_postgres
    engine, Session = get_engine_and_session(use_postgres)
    Base.metadata.create_all(bind=engine)
    session = Session()

    try:
        while True:
            jobs = fetch_next_jobs(session, args.limit)
            if not jobs:
                if not args.loop:
                    print("No pending jobs.")
                    break
                time.sleep(args.sleep)
                continue

            for job in jobs:
                print(f"Processing job {job.id}: {job.unit_kind} {job.name} {job.variant or ''} mul_type={job.mul_type}")
                process_job(session, job)

            if not args.loop:
                break
            time.sleep(args.sleep)
    finally:
        session.close()


if __name__ == "__main__":
    main()
